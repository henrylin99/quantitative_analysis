"""全市场分钟线同步编排：pytdx 源 → stock_minute 分区，支持断点续传与失败冷却。

批次 3.2：目标全市场 ≥5000 只 5min 数据按交易日持续更新。
数据源结论（详见记忆 minute-kline-source-pytdx-only）：分钟级 K 线唯一可用
源是 pytdx（服务器 IP 常换，取数器内置动态主机探测）；baostock/akshare/
tickflow/tushare 分钟线均不可用，勿再尝试。

设计要点：
- **断点续传**：进度状态落 `data/minute_sync/state.json`（已完成代码清单 +
  失败计数），中断/冷却后下次运行跳过已完成代码，只补剩余部分；
- **失败冷却**：连续多只股票请求失败（默认 30 只）判定为数据源不可用/断网，
  立即停手保存状态——避免无意义请求拖慢调度链；
- **增量/回填两档**：增量取最近 600 根（约 12 个交易日，容忍节假日中断）；
  回填由 TdxMinuteFetcher 向前翻页至 start_date（缺省 6 个月滚动窗口）；
- **不阻塞预警**：晚间调度链中作为最后一步运行，异常只记日志不外抛；
- 存储写入统一走 MinuteParquetStore（tushare 风格代码 + 双风格去重）。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd
from loguru import logger

from app.services.minute_parquet_store import MinuteParquetStore

#: 增量拉取根数：48 根/日 × 12 交易日 + 余量
_INCREMENTAL_BARS = 600


class MinuteMarketSyncService:
    def __init__(self, data_dir: str | None = None, client_factory: Optional[Callable[[], object]] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = Path(data_dir)
        self.parquet_store = MinuteParquetStore(data_dir=str(self.data_dir))
        self.state_path = self.data_dir / "minute_sync" / "state.json"
        self._client_factory = client_factory or self._default_client_factory
        self._client = None

    # ---- 客户端 ----

    @staticmethod
    def _default_client_factory():
        from app.services.minute_tdx_fetcher import TdxMinuteFetcher

        return TdxMinuteFetcher()

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    # ---- 股票清单 ----

    @staticmethod
    def load_stock_universe() -> List[str]:
        """上市中（list_status=L）股票代码，tushare 风格。"""
        from app.services.data_reader import ParquetDataReader

        df = ParquetDataReader().get_stock_basic()
        if df.empty or "ts_code" not in df.columns:
            logger.warning("stock_basic 为空，无法构建全市场清单")
            return []
        if "list_status" in df.columns:
            df = df[df["list_status"] == "L"]
        return df["ts_code"].dropna().astype(str).tolist()

    # ---- 状态（断点续传）----

    def load_state(self) -> Dict:
        if self.state_path.is_file():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"minute_sync 状态文件损坏，重置: {exc}")
        return self._new_state("")

    @staticmethod
    def _new_state(mode: str) -> Dict:
        return {
            "mode": mode,
            "run_id": "",
            "total": 0,
            "done_codes": [],
            "failed": {},
            "cooldown": False,
            "started_at": None,
            "updated_at": None,
            "finished_at": None,
            "last_message": None,
        }

    def save_state(self, state: Dict) -> None:
        state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_path)

    def get_progress(self) -> Dict:
        """给 API/UI 的进度视图（不含逐只失败明细，聚合为计数）。"""
        state = self.load_state()
        done, failed = len(state.get("done_codes", [])), len(state.get("failed", {}))
        return {
            "mode": state.get("mode"),
            "run_id": state.get("run_id"),
            "total": state.get("total", 0),
            "done": done,
            "failed": failed,
            "running": self._is_running(state),
            "cooldown": bool(state.get("cooldown")),
            "started_at": state.get("started_at"),
            "updated_at": state.get("updated_at"),
            "finished_at": state.get("finished_at"),
            "last_message": state.get("last_message"),
        }

    # ---- 同步 ----

    def sync_market(
        self,
        period_type: str = "5min",
        mode: str = "incremental",
        start_date: str | None = None,
        stock_list: List[str] | None = None,
        cooldown_failures: int = 30,
        per_call_sleep: float | None = None,
    ) -> Dict:
        """全市场同步。mode: incremental（增量）/ backfill（回填到 start_date）。

        断点续传：上次运行未结束（冷却/中断）且 mode 相同时，跳过已完成代码
        继续跑；参数变化则开新 run。返回汇总 dict；中途冷却时 success=False。
        """
        if mode not in ("incremental", "backfill"):
            raise ValueError(f"unsupported sync mode: {mode}")
        universe = stock_list if stock_list is not None else self.load_stock_universe()
        if not universe:
            return {"success": False, "message": "股票清单为空，未同步"}

        prev = self.load_state()
        if self._is_running(prev):
            return {"success": False, "message": f"已有同步在运行（run {prev.get('run_id')}），本次跳过"}

        resume_from = prev if self._resumable(prev, mode) else None
        if resume_from:
            done_set = set(resume_from.get("done_codes", []))
            state = resume_from
            state["failed"] = {}
            universe = [c for c in universe if c not in done_set]
            logger.info(f"分钟同步续传 run {state['run_id']}：已完成 {len(done_set)}，剩余 {len(universe)}")
            if not universe:
                return {"success": True, "message": "上次运行已覆盖全部股票，无需续传",
                        "total_stocks": state.get("total", 0), "rows_written": 0}
        else:
            state = self._new_state(mode)
            state["run_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
            state["started_at"] = datetime.now().isoformat(timespec="seconds")
        state["total"] = len(stock_list) if stock_list is not None else max(len(universe), len(state.get("done_codes", [])))
        state["cooldown"] = False
        self.save_state(state)

        rows_written = 0
        consecutive_failures = 0
        cooldown_reason = None
        failed: Dict[str, str] = {}

        for idx, ts_code in enumerate(universe, start=1):
            try:
                rows = self._sync_single(ts_code, period_type, mode, start_date, per_call_sleep)
                rows_written += rows
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                consecutive_failures += 1
                failed[ts_code] = str(exc)[:200]
                if consecutive_failures >= cooldown_failures:
                    cooldown_reason = (
                        f"连续 {consecutive_failures} 只失败，疑似数据源限流，冷却断点："
                        f"剩余 {len(universe) - idx + 1} 只待续传"
                    )
                    logger.error(cooldown_reason)
                    break
                continue  # 失败但不冷却：不标 done，下次运行重试

            state["done_codes"].append(ts_code)
            state["failed"] = failed
            if idx % 50 == 0:
                state["last_message"] = f"{len(state['done_codes'])}/{state['total']} 只，本轮拉取 {rows_written} 行"
                self.save_state(state)

        state["failed"] = failed
        state["last_message"] = cooldown_reason or (
            f"完成：本轮成功 {len(universe) - len(failed)}/{len(universe)} 只，拉取 {rows_written} 行，"
            f"失败 {len(failed)} 只"
        )
        if cooldown_reason is None:
            state["finished_at"] = datetime.now().isoformat(timespec="seconds")
        state["cooldown"] = cooldown_reason is not None
        self.save_state(state)
        return {
            "success": cooldown_reason is None,
            "message": state["last_message"],
            "total_stocks": state["total"],
            "success_stocks": len(universe) - len(failed),
            "failed_stocks": len(failed),
            "rows_written": rows_written,
            "period_type": period_type,
            "mode": mode,
            "run_id": state["run_id"],
        }

    def _is_running(self, state: Dict) -> bool:
        """状态显示未结束、非冷却待续传、且 30 分钟内有心跳 → 判定有并发运行。"""
        if not state.get("run_id") or state.get("finished_at"):
            return False
        if state.get("cooldown"):
            return False
        updated = state.get("updated_at")
        if not updated:
            return False
        try:
            age = datetime.now() - datetime.fromisoformat(updated)
        except ValueError:
            return False
        return age.total_seconds() < 30 * 60

    def _resumable(self, state: Dict, mode: str) -> bool:
        """冷却中止或异常中断（未完成）且模式相同 → 可续传。"""
        return bool(state.get("run_id")) and state.get("finished_at") is None and state.get("mode") == mode

    def _sync_single(
        self, ts_code: str, period_type: str, mode: str, start_date: str | None, per_call_sleep: float | None
    ) -> int:
        client = self._get_client()
        if mode == "incremental":
            df = client.fetch_latest(ts_code, period_type=period_type, limit=_INCREMENTAL_BARS)
        else:
            # 回填：取数器内部向前翻页直至覆盖 start_date（缺省约 6 个月）
            floor = start_date or (datetime.now() - timedelta(days=185)).strftime("%Y%m%d")
            df = client.fetch_range(ts_code, period_type, floor)
        self._pause(per_call_sleep)
        self._write(df, period_type)
        # 上报口径取拉取行数（store.write_frame 返回的是分区总行数，非新增）
        return int(len(df))

    @staticmethod
    def _pause(per_call_sleep: float | None) -> None:
        if per_call_sleep:
            time.sleep(per_call_sleep)

    def _write(self, df: pd.DataFrame, period_type: str) -> int:
        if df.empty:
            return 0
        if "pre_close" not in df.columns:
            # 与既有分钟 schema 对齐：链内 shift 计算 pre_close/change/pct_chg
            df = df.sort_values("datetime").reset_index(drop=True)
            df["pre_close"] = df.groupby("ts_code")["close"].shift(1)
            first_mask = df["pre_close"].isna()
            df.loc[first_mask, "pre_close"] = df.loc[first_mask, "close"]
            df["change"] = df["close"] - df["pre_close"]
            df["pct_chg"] = (df["change"] / df["pre_close"] * 100).fillna(0).round(4)
            df.loc[first_mask, ["change", "pct_chg"]] = [0, 0]
        return int(self.parquet_store.write_frame(df, period_type))
