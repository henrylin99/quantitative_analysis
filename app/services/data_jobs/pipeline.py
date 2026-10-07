"""数据链路自动编排 + 完整性巡检。

背景：平台唯一的自动定时任务曾是每日预警扫描，而预警消费的行情/资金流/
筹码数据全靠人工在页面逐个提交作业——"预警跑了但数据还是旧的"是现实风险。

本模块提供两件事：

1. DataPipelineOrchestrator：收盘后按依赖顺序串行跑完整数据链路
   （交易日历 → 日线 → 基本指标 → 资金流 → 扩展因子 → 筹码 → 大宽表 →
   股票分区重建 → 因子计算），每步等上一步成功再提交下一步，一步失败
   即中止链路。由 DailyAlertScheduler 在预警扫描之前触发（可关）。
2. DataFreshnessService：读各表日期分区的最新日期，对照交易日历给出
   每表滞后交易天数；巡检结果并入每日预警（滞后 ≥1 交易日 → warn）。

非交易日链路自动跳过（无新数据可下）。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

# 收盘后链路顺序（与 JobRegistry 的 dependencies 一致的可行拓扑序）
PIPELINE_JOBS = (
    "trade_calendar",
    "daily_history_by_date",
    "daily_basic",
    "moneyflow",
    "stk_factor",
    "cyq_perf",
    "wide_table_builder",
    "stock_partition_rebuild",
    "factor_compute",
)

# 新鲜度巡检的表：名称 → daily 日期分区相对路径
FRESHNESS_TABLES = {
    "daily_history": "daily_history/daily",
    "daily_basic": "daily_basic/daily",
    "stk_factor": "stk_factor/daily",
    "moneyflow": "moneyflow/daily",
    "cyq_perf": "cyq_perf/daily",
    "adj_factor": "adj_factor/daily",
}
FACTOR_VALUES_REL = "ml_factor_state/factor_values"

_CALENDAR_FILE = "stock_trade_calendar.parquet"
_PIPELINE_LOG = "pipeline_runs.json"
_MAX_PIPELINE_LOGS = 30
_POLL_INTERVAL = 5.0

_chain_lock = threading.Lock()
_chain_running = threading.Event()


def resolve_data_dir(data_dir: Optional[str] = None) -> Path:
    if data_dir:
        return Path(data_dir)
    return Path(
        os.getenv("DATA_DIR",
                  os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
    )


def _latest_hive_date(partition_dir: Path) -> Optional[str]:
    """year=/month=/day= 嵌套分区的最新日期（YYYY-MM-DD）。"""
    latest = None
    if not partition_dir.exists():
        return None
    for year_dir in partition_dir.glob("year=*"):
        for month_dir in year_dir.glob("month=*"):
            for day_dir in month_dir.glob("day=*"):
                d = f"{year_dir.name.split('=')[1]}-{month_dir.name.split('=')[1]}-{day_dir.name.split('=')[1]}"
                if latest is None or d > latest:
                    latest = d
    return latest


def _latest_trade_date_partition(partition_dir: Path) -> Optional[str]:
    """trade_date=YYYY-MM-DD 平铺分区的最新日期。"""
    if not partition_dir.exists():
        return None
    latest = None
    for d in partition_dir.glob("trade_date=*"):
        v = d.name.split("=", 1)[1]
        if latest is None or v > latest:
            latest = v
    return latest


def load_trade_calendar(data_dir: Path) -> List[str]:
    """升序返回 is_open==1 的交易日（YYYY-MM-DD），读不到返回 []。"""
    path = data_dir / _CALENDAR_FILE
    try:
        cal = pd.read_parquet(path)
        open_days = cal[cal["is_open"] == 1]["cal_date"].astype(str)
        # 日历存在两种格式（20260101 / 2026-01-01），统一成 YYYY-MM-DD
        normalized = sorted({d if "-" in d else f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in open_days})
        return normalized
    except Exception as e:
        logger.warning(f"读取交易日历失败: {e}")
        return []


class DataFreshnessService:
    """各数据表相对最新交易日的滞后巡检。"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = resolve_data_dir(data_dir)

    def status(self) -> Dict[str, Any]:
        open_days = load_trade_calendar(self.data_dir)
        today = datetime.now().strftime("%Y-%m-%d")
        expected = None
        for d in reversed(open_days):
            if d <= today:
                expected = d
                break

        rows: List[Dict[str, Any]] = []
        for name, rel in FRESHNESS_TABLES.items():
            latest = _latest_hive_date(self.data_dir / rel)
            rows.append(self._row(name, latest, expected, open_days))
        rows.append(self._row(
            "factor_values",
            _latest_trade_date_partition(self.data_dir / FACTOR_VALUES_REL),
            expected, open_days,
        ))

        lagged = [r for r in rows if not r["ok"]]
        return {
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "expected_date": expected,
            "has_calendar": bool(open_days),
            "tables": rows,
            "lagged_tables": [r["table"] for r in lagged],
            "all_fresh": not lagged,
        }

    @staticmethod
    def _row(table: str, latest: Optional[str], expected: Optional[str],
             open_days: List[str]) -> Dict[str, Any]:
        lag = None
        if latest and expected and open_days:
            try:
                i_latest = open_days.index(latest)
                i_exp = open_days.index(expected)
                lag = i_exp - i_latest  # 交易天数滞后
            except ValueError:
                lag = None
        ok = lag is not None and lag <= 0
        return {
            "table": table,
            "latest_date": latest,
            "expected_date": expected,
            "lag_trading_days": lag,
            "ok": ok,
        }


class DataPipelineOrchestrator:
    """收盘后链路串行编排。"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = resolve_data_dir(data_dir)

    # ------------------------------------------------------------------
    @property
    def _log_path(self) -> Path:
        return self.data_dir / "data_job_state" / _PIPELINE_LOG

    @staticmethod
    def enabled() -> bool:
        return os.getenv("DATA_PIPELINE_ENABLED", "1") not in ("0", "false", "False")

    def list_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            with open(self._log_path, encoding="utf-8") as f:
                return json.load(f).get("runs", [])[-limit:]
        except Exception:
            return []

    def _append_run(self, run: Dict[str, Any]) -> None:
        try:
            runs = self.list_runs(1000)
            runs.append(run)
            runs = runs[-_MAX_PIPELINE_LOGS:]
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self._log_path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"runs": runs}, f, ensure_ascii=False)
            os.replace(tmp, self._log_path)
        except Exception:
            logger.warning("写链路运行日志失败", exc_info=True)

    # ------------------------------------------------------------------
    def is_trading_today(self) -> tuple:
        open_days = load_trade_calendar(self.data_dir)
        if not open_days:
            return True, "无交易日历（默认按交易日处理）"
        today = datetime.now().strftime("%Y-%m-%d")
        if today in open_days:
            return True, "今日为交易日"
        return False, "今日非交易日，跳过链路"

    def run_chain(self, job_types: Optional[List[str]] = None,
                  abort_on_error: bool = True) -> Dict[str, Any]:
        """串行提交并等待整条链路；同刻只允许一条链路在跑。"""
        if _chain_running.is_set():
            return {"ok": False, "message": "已有一条数据链路在运行中"}
        with _chain_lock:
            if _chain_running.is_set():
                return {"ok": False, "message": "已有一条数据链路在运行中"}
            _chain_running.set()
        try:
            return self._run_chain_inner(job_types or list(PIPELINE_JOBS), abort_on_error)
        finally:
            _chain_running.clear()

    def _run_chain_inner(self, job_types: List[str], abort_on_error: bool) -> Dict[str, Any]:
        from app.services.data_jobs.service import DataJobService

        started = datetime.now()
        trading, trading_msg = self.is_trading_today()
        run_record: Dict[str, Any] = {
            "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
            "trigger": "manual" if job_types != list(PIPELINE_JOBS) else "chain",
            "is_trading_day": trading,
            "steps": [],
            "ok": False,
        }
        if not trading:
            run_record["message"] = trading_msg
            run_record["ok"] = True
            run_record["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._append_run(run_record)
            return {"ok": True, **run_record}

        svc = DataJobService()
        ok = True
        message = ""
        for job_type in job_types:
            step: Dict[str, Any] = {"job_type": job_type, "started_at": datetime.now().strftime("%H:%M:%S")}
            try:
                run = svc.submit(job_type)
                step["run_id"] = run.id
                final = self._wait_run(svc, run.id)
                step["status"] = getattr(final, "status", "unknown")
                step["message"] = getattr(final, "progress_message", None)
                if getattr(final, "status", "") != "success":
                    ok = False
                    message = f"{job_type} 结束于 {step['status']}"
            except Exception as e:
                ok = False
                message = f"{job_type} 提交/等待失败: {e}"
                step["status"] = "error"
                step["message"] = message
            step["finished_at"] = datetime.now().strftime("%H:%M:%S")
            run_record["steps"].append(step)
            logger.info(f"数据链路 {job_type}: {step.get('status')} ({step['started_at']} → {step['finished_at']})")
            if not ok and abort_on_error:
                break

        run_record["ok"] = ok
        run_record["message"] = message or "链路完成"
        run_record["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._append_run(run_record)
        return {"ok": ok, **run_record}

    @staticmethod
    def _wait_run(svc, run_id: int, timeout: float = 5400.0):
        """轮询等待单个作业结束（success/failed/cancelled 等终态）。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = svc.get_run(run_id)
            status = str(getattr(run, "status", "") or "")
            if status not in ("queued", "running", "pending", ""):
                return run
            time.sleep(_POLL_INTERVAL)
        return svc.get_run(run_id)

    def start_background(self, job_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """后台线程跑链路（API 触发入口）；立刻返回。"""
        if _chain_running.is_set():
            return {"ok": False, "message": "已有一条数据链路在运行中"}

        def _work():
            try:
                self.run_chain(job_types=job_types)
            except Exception:
                logger.error("数据链路后台运行失败", exc_info=True)

        threading.Thread(target=_work, name="data-pipeline-chain", daemon=True).start()
        return {"ok": True, "message": "数据链路已启动，可在运行记录中查看进度"}
