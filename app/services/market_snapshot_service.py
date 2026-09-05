"""行情快照服务：扶摇实时数据的缓存聚合层。

职责：
- 对快照/看板/龙虎榜/风向标做 TTL 或按日缓存，避免多页面轮询打爆扶摇限频
- 看板聚合：涨跌家数、涨跌停近似统计、涨跌分布、榜单（涨幅/跌幅/成交额）
- 降级：扶摇异常时回退本地 Parquet 最近交易日的日线数据计算看板，
  并标记 degraded=True（前端据此展示降级提示，而不是白屏）

口径说明：
- 涨跌停家数为近似统计：按代码板块推断涨跌停幅度（北交所 30%、创业板/
  科创板 20%、其余 10%），不含 ST 的 5% 特例，也无法感知除权除息，
  仅用于市场宽度展示，不作为交易依据
- 快照无股票名称字段，name 由本地 stock_basic 关联补齐
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from app.utils.data_sources.fuyao_client import FuyaoClient, FuyaoError
from app.utils.data_sources.fuyao_normalize import snapshot_rows_to_quote_frame

DASHBOARD_CACHE_SECONDS = 30.0
QUOTES_CACHE_SECONDS = 5.0
STALE_SERVE_SECONDS = 600.0  # 扶摇异常时，最近一次成功数据在 10 分钟内继续供应
SOURCE_STATUS_CACHE_SECONDS = 300.0
INDICES_FRESH_SECONDS = 10.0
#: 龙虎榜/竞价 date=None（"最近发布日"）的短缓存——发布时点未知，不能按日缓存
LATEST_DAY_FRESH_SECONDS = 300.0
#: 指定历史日的榜单是定稿数据，长缓存即可
DAY_FINAL_TTL_SECONDS = 24 * 3600.0
#: 按日缓存容量上限（防多日期轮询导致无界增长）
DAY_CACHE_MAX_ENTRIES = 64


def evict_oldest(cache: Dict[Any, Tuple[float, Any]], max_entries: int) -> None:
    """按写入时间淘汰最旧条目，调用方须已持有锁。"""
    while len(cache) >= max_entries:
        oldest = min(cache.items(), key=lambda kv: kv[1][0])[0]
        cache.pop(oldest)

#: 看板默认指数（上证指数/深证成指/创业板指/沪深300）
DEFAULT_INDEX_CODES = ("000001.SH", "399001.SZ", "399006.SZ", "000300.SH")


def _limit_ratio_for(ts_code: str) -> float:
    """按代码板块推断涨跌停幅度（近似口径，见模块 docstring）。"""
    code = ts_code.split(".")[0]
    if ts_code.endswith(".BJ"):
        return 0.30
    if code.startswith(("300", "688", "689")):
        return 0.20
    return 0.10


class MarketSnapshotService:
    """进程内单例（get_market_snapshot_service），线程安全。"""

    def __init__(self, client: Optional[FuyaoClient] = None):
        self._client = client
        self._lock = threading.Lock()
        self._dashboard_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._quotes_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._dragon_cache: Dict[Tuple[str, Optional[str]], Tuple[float, Dict[str, Any]]] = {}
        self._auction_cache: Dict[Optional[str], Tuple[float, Dict[str, Any]]] = {}
        self._status_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._frame_cache: Optional[Tuple[float, "pd.DataFrame"]] = None
        self._indices_cache: Dict[Tuple[str, ...], Tuple[float, List[Dict[str, Any]]]] = {}

    # ---- 基础 ----

    @property
    def client(self) -> FuyaoClient:
        if self._client is None:
            self._client = FuyaoClient()
        return self._client

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _merge_stock_names(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """快照无名称字段，用名称注册表补齐（stock_basic + TickFlow 兜底）。"""
        try:
            from app.services.stock_name_registry import get_stock_name_registry

            return get_stock_name_registry().merge_names(rows)
        except Exception as exc:  # noqa: BLE001 - 名称补齐失败不影响行情主数据
            logger.debug(f"[market] 名称补齐跳过: {exc}")
            return rows

    # ---- 实时快照 ----

    def get_quotes(self, ts_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """按代码取实时快照（≤100 只/请求，自动分批；单只缓存 5s）。

        返回 {ts_code: {ts_code,name,last_price,pct_chg,...}}；取不到的代码
        不出现在结果里。扶摇异常时回退缓存中的旧值（10 分钟内）。
        """
        wanted = list(dict.fromkeys(ts_codes or []))[:200]
        result: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []
        now = time.monotonic()
        with self._lock:
            for code in wanted:
                cached = self._quotes_cache.get(code)
                if cached and now - cached[0] < QUOTES_CACHE_SECONDS:
                    result[code] = cached[1]
                else:
                    missing.append(code)

        if missing:
            fresh = self._fetch_quote_rows(missing)
            with self._lock:
                for row in fresh:
                    code = str(row.get("ts_code"))
                    self._quotes_cache[code] = (time.monotonic(), row)
                    result[code] = row

        return {code: result[code] for code in wanted if code in result}

    def _fetch_quote_rows(self, ts_codes: List[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            for start in range(0, len(ts_codes), 100):
                batch = ts_codes[start:start + 100]
                data = self.client.snapshot_page(thscodes=batch)
                rows.extend(data.get("item") or [])
            frame = snapshot_rows_to_quote_frame(rows)
        except FuyaoError as exc:
            logger.warning(f"[market] 快照批量拉取失败，回退缓存: {exc}")
            return self._stale_quotes(ts_codes)
        return self._merge_stock_names(frame.to_dict("records"))

    def _stale_quotes(self, ts_codes: List[str]) -> List[Dict[str, Any]]:
        now = time.monotonic()
        stale: List[Dict[str, Any]] = []
        with self._lock:
            for code in ts_codes:
                cached = self._quotes_cache.get(code)
                if cached and now - cached[0] < STALE_SERVE_SECONDS:
                    stale.append(cached[1])
        return stale

    # ---- 看板 ----

    def get_dashboard(self) -> Dict[str, Any]:
        """市场看板聚合（缓存 30s；扶摇异常降级本地 Parquet 最近交易日）。"""
        with self._lock:
            cached = self._dashboard_cache
        if cached and time.monotonic() - cached[0] < DASHBOARD_CACHE_SECONDS:
            return cached[1]

        try:
            rows, server_ts = self.client.snapshot_all()
            if not rows:
                raise FuyaoError("empty", "快照为空")
            frame = snapshot_rows_to_quote_frame(rows)
            frame = self._merge_stock_names(frame.to_dict("records"))
            frame = pd.DataFrame(frame)
            with self._lock:
                self._frame_cache = (time.monotonic(), frame)
            payload = self._build_dashboard(frame, source="fuyao", as_of=None)
            payload["server_ts"] = server_ts
        except FuyaoError as exc:
            logger.warning(f"[market] 看板实时数据失败，降级本地 Parquet: {exc}")
            payload = self._dashboard_from_local()
            payload["degraded_reason"] = str(exc)

        with self._lock:
            self._dashboard_cache = (time.monotonic(), payload)
        return payload

    def get_quote_frame(self) -> Optional["pd.DataFrame"]:
        """全市场实时快照 DataFrame（复用看板 30s 缓存；无数据返回 None）。

        列为扶摇快照 schema（last_price/pct_chg/turnover 元）或降级时的
        本地日线 schema（close/pre_close/amount 千元），调用方两种都要兼容。
        """
        try:
            self.get_dashboard()
        except Exception:  # noqa: BLE001 - 看板失败不阻断帧读取
            pass
        with self._lock:
            cached = self._frame_cache
        return cached[1] if cached else None

    def _dashboard_from_local(self) -> Dict[str, Any]:
        """降级：用本地日线最近分区构建看板（标记 degraded + as_of）。"""
        from app.utils.parquet_job_helpers import latest_partition_date

        data_dir = None
        latest = latest_partition_date("daily_history/daily", data_dir=data_dir)
        if not latest:
            return {
                "degraded": True, "source": "none", "as_of": None,
                "indices": [], "breadth": {}, "distribution": [],
                "top_gainers": [], "top_losers": [], "top_amount": [],
                "updated_at": self._now_ms(),
            }
        from app.services.data_reader import ParquetDataReader

        df = ParquetDataReader().get_daily(start_date=latest, end_date=latest)
        with self._lock:
            self._frame_cache = (time.monotonic(), df)
        payload = self._build_dashboard(df, source="local_parquet", as_of=latest)
        payload["degraded"] = True
        return payload

    @staticmethod
    def _build_dashboard(frame: "pd.DataFrame", source: str, as_of: Optional[str]) -> Dict[str, Any]:
        """把两套列名（扶摇快照 / 本地日线）统一成看板聚合的输入契约。"""
        import pandas as pd

        from app.services.market_dashboard import build_dashboard_payload

        unified = pd.DataFrame({"ts_code": frame["ts_code"].astype(str)})
        unified["name"] = frame["name"] if "name" in frame.columns else None
        unified["price"] = frame["last_price"] if "last_price" in frame.columns else frame["close"]
        unified["pct_chg"] = pd.to_numeric(frame["pct_chg"], errors="coerce")
        unified["prev_close"] = (
            frame["prev_close"] if "prev_close" in frame.columns else frame["pre_close"]
        )
        if "turnover" in frame.columns:  # 扶摇：元
            unified["amount_yuan"] = pd.to_numeric(frame["turnover"], errors="coerce")
        else:  # 本地日线：千元 → 元
            unified["amount_yuan"] = pd.to_numeric(frame["amount"], errors="coerce") * 1000.0

        payload = build_dashboard_payload(unified)
        payload.update({"degraded": False, "source": source, "as_of": as_of})
        return payload

    # ---- 指数 ----

    def get_indices(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """指数实时快照（默认看板四指数；北交所指数不支持，自动跳过）。

        缓存 10 秒；扶摇异常时回供 10 分钟内的旧值，再退返回 []。
        """
        wanted = [s for s in (symbols or list(DEFAULT_INDEX_CODES)) if not s.upper().endswith(".BJ")]
        key = tuple(wanted)
        with self._lock:
            cached = self._indices_cache.get(key)
        if cached and time.monotonic() - cached[0] < INDICES_FRESH_SECONDS:
            return copy.deepcopy(cached[1])
        try:
            rows, _ = self.client.index_snapshot(wanted)
        except FuyaoError as exc:
            if cached and time.monotonic() - cached[0] < STALE_SERVE_SECONDS:
                logger.warning(f"[market] 指数快照失败，回供过期缓存: {exc}")
                return copy.deepcopy(cached[1])
            logger.warning(f"[market] 指数快照失败: {exc}")
            return []
        result = [
            {
                "ts_code": row.get("thscode"),
                "last_price": row.get("last_price"),
                "pct_chg": row.get("price_change_ratio_pct"),
            }
            for row in rows
        ]
        with self._lock:
            evict_oldest(self._indices_cache, DAY_CACHE_MAX_ENTRIES)
            self._indices_cache[key] = (time.monotonic(), result)
        return result

    # ---- 龙虎榜 / 竞价风向标 ----
    # date=None 表示"最近发布日"，发布时点未知（龙虎榜收盘后才出），只做短缓存；
    # 指定历史日的榜单是定稿数据，可长缓存；两种键都设容量上限防无界增长。

    @staticmethod
    def _day_data_fresh(date: Optional[str]) -> float:
        return LATEST_DAY_FRESH_SECONDS if date is None else DAY_FINAL_TTL_SECONDS

    def _fetch_day_payload(
        self,
        cache: Dict[Any, Tuple[float, Dict[str, Any]]],
        key: Any,
        date: Optional[str],
        fetch,
    ) -> Dict[str, Any]:
        """按日数据通用获取：TTL 缓存 + 过期回供 + 容量上限。"""
        fresh = self._day_data_fresh(date)
        with self._lock:
            cached = cache.get(key)
        if cached and time.monotonic() - cached[0] < fresh:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload
        try:
            payload = fetch()
        except FuyaoError as exc:
            if cached and time.monotonic() - cached[0] < fresh + STALE_SERVE_SECONDS:
                logger.warning(f"[market] 按日数据拉取失败，回供过期缓存: {exc}")
                payload = copy.deepcopy(cached[1])
                payload.update({"cached": True, "stale": True})
                return payload
            raise
        with self._lock:
            evict_oldest(cache, DAY_CACHE_MAX_ENTRIES)
            # 写入侧也深拷贝：缓存中的对象与首次返回给调用方的对象必须隔离
            cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    def get_dragon_tiger(self, board_type: str = "all", date: Optional[str] = None) -> Dict[str, Any]:
        return self._fetch_day_payload(
            self._dragon_cache,
            (board_type, date),
            date,
            lambda: self.client.dragon_tiger_list(board_type=board_type, date=date),
        )

    def get_auction_benchmark(self, date: Optional[str] = None) -> Dict[str, Any]:
        return self._fetch_day_payload(
            self._auction_cache,
            date,
            date,
            lambda: self.client.short_term_benchmark(date=date),
        )

    # ---- 数据源状态 ----

    def get_source_status(self, force: bool = False) -> Dict[str, Any]:
        """三数据源健康状态（缓存 5 分钟）。

        tushare 只做 token 配置检查（不 burn 积分）；fuyao/tickflow 发最小
        探测请求。
        """
        with self._lock:
            cached = self._status_cache
        if cached and not force and time.monotonic() - cached[0] < SOURCE_STATUS_CACHE_SECONDS:
            return cached[1]

        status: Dict[str, Any] = {"checked_at": self._now_ms()}

        tushare_token = (_env("TUSHARE_TOKEN") or "").strip()
        status["tushare"] = {"configured": tushare_token not in ("", "your_tushare_token")}

        fuyao_key = (_env("FUYAO_API_KEY") or "").strip()
        fuyao_status: Dict[str, Any] = {"configured": bool(fuyao_key)}
        if fuyao_key:
            try:
                self.client.snapshot_page(limit=1)
                fuyao_status.update({"ok": True, "error": None})
            except FuyaoError as exc:
                fuyao_status.update({"ok": False, "error": str(exc)})
        status["fuyao"] = fuyao_status

        from app.utils.data_sources.tickflow_client import TickflowClient

        tickflow_key = (_env("TICKFLOW_API_KEY") or "").strip()
        tier = TickflowClient(api_key=tickflow_key).detect_tier() if tickflow_key else "none"
        status["tickflow"] = {"configured": bool(tickflow_key), "tier": tier}

        with self._lock:
            self._status_cache = (time.monotonic(), status)
        return status


def _env(key: str) -> Optional[str]:
    import os

    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv(key)


_service: Optional[MarketSnapshotService] = None
_service_lock = threading.Lock()


def get_market_snapshot_service() -> MarketSnapshotService:
    global _service
    with _service_lock:
        if _service is None:
            _service = MarketSnapshotService()
        return _service
