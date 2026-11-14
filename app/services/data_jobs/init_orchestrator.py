"""数据初始化编排（新项目从零建库）。

面向"空库首启"场景：用户配好 token 后一键按阶段下载核心数据并派生宽表/
分区/因子。与盘后 pipeline（增量更新）互补：

- tushare 行情类默认下载 1 年（用户可改），财务（fuyao 源）默认 10 年；
- 分阶段串行，每步复用 DataJobService（独立 run 记录、progress/progress_message）；
- 进度实时落盘 data/data_job_state/init_run.json，前端轮询 GET 状态渲染；
- 与 pipeline 共用 _chain_running 互斥锁，避免初始化与盘后链路同时写库。

动态补齐：每步启动前检查 data/ 目录下该步产物是否已存在（文件非空 /
分区覆盖请求窗口），已存在则标记 skipped 跳过，只补缺失部分——中断后
重跑、或数据由其它途径（手工作业/历史库）落盘时无需重头下载。

阶段顺序（依赖拓扑）：
  1 基础元数据：stock_basic → trade_calendar
  2 tushare 日频（带年份窗口）：daily_history_by_date → daily_basic →
    index_daily → moneyflow
  3 派生：wide_table_builder → stock_partition_rebuild
  4 fuyao 财务三表（默认 10 年窗口）：financial_fuyao
  5 因子：factor_compute → fundamental_pit_compute
  6 预置：seed_strategies（常用策略，缺哪个补哪个，不走 DataJobService）
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.data_jobs.pipeline import (
    _chain_lock,
    _chain_running,
    _POLL_INTERVAL,
    resolve_data_dir,
)

DEFAULT_TUSHARE_YEARS = 1
DEFAULT_FINANCIAL_YEARS = 10
_MAX_YEARS = 30

_INIT_STATE_RELPATH = "data_job_state/init_run.json"
_MAX_RECORDS = 20

# 用户中断（模块级：API 每次请求新建 orchestrator 实例，须跨实例共享）
_cancel_event = threading.Event()

# 运行态心跳：正常链路每 ~2s 刷一次进度；超过该窗口无心跳视为已死
# （步骤间空档也会整体重写状态文件，正常不会误判）
_STALE_HEARTBEAT_SECONDS = 900

# (job_type, 是否用 tushare 年份窗口)；None = 元数据/派生作业不传窗口
INIT_PLAN: List[Dict[str, Any]] = [
    {"job_type": "stock_basic", "range": None, "label": "股票基础资料"},
    {"job_type": "stock_company", "range": None, "label": "公司信息"},
    {"job_type": "trade_calendar", "range": None, "label": "交易日历"},
    {"job_type": "daily_history_by_date", "range": "tushare", "label": "日线行情"},
    {"job_type": "daily_basic", "range": "tushare", "label": "每日基本指标"},
    {"job_type": "adj_factor", "range": "tushare", "label": "复权因子"},
    {"job_type": "index_daily", "range": None, "label": "指数日线"},
    {"job_type": "moneyflow", "range": "tushare", "label": "资金流向"},
    {"job_type": "wide_table_builder", "range": None, "label": "大宽表构建"},
    {"job_type": "stock_partition_rebuild", "range": None, "label": "股票分区重建"},
    {"job_type": "financial_fuyao", "range": "financial", "label": "财务三表（扶摇）"},
    {"job_type": "factor_compute", "range": None, "label": "因子计算"},
    {"job_type": "fundamental_pit_compute", "range": None, "label": "基本面 PIT 因子"},
    {"job_type": "seed_strategies", "range": None, "label": "常用策略预置"},
]


class DataInitOrchestrator:
    """一次性初始化编排器（无状态，进度持久化到 JSON）。"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = resolve_data_dir(data_dir)
        self.state_path = self.data_dir / _INIT_STATE_RELPATH

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def start(self, tushare_years: int = DEFAULT_TUSHARE_YEARS,
              financial_years: int = DEFAULT_FINANCIAL_YEARS) -> Dict[str, Any]:
        """后台线程启动初始化链（与 pipeline 互斥）；立即返回。"""
        tushare_years = _clamp_years(tushare_years, DEFAULT_TUSHARE_YEARS)
        financial_years = _clamp_years(financial_years, DEFAULT_FINANCIAL_YEARS)

        if _chain_running.is_set():
            return {"ok": False, "message": "已有一条数据链路/初始化在运行中"}

        with _chain_lock:
            if _chain_running.is_set():
                return {"ok": False, "message": "已有一条数据链路/初始化在运行中"}
            _chain_running.set()

        _cancel_event.clear()
        record = self._new_record(tushare_years, financial_years)
        self._write_state(record, running=True)

        def _work():
            try:
                self._run_plan(record)
            except Exception:
                logger.exception("数据初始化后台运行失败")
                record["ok"] = False
                record["message"] = "初始化链路异常中断（详见服务日志）"
                record["finished_at"] = _now()
                self._write_state(record, running=False)
            finally:
                _chain_running.clear()

        threading.Thread(target=_work, name="data-init-chain", daemon=True).start()
        return {"ok": True, "message": "数据初始化已启动", "steps_total": len(INIT_PLAN)}

    def cancel(self) -> Dict[str, Any]:
        """请求中断：当前步骤跑完后停止后续步骤（子作业不硬杀，防写坏分区）。"""
        if not _chain_running.is_set():
            return {"ok": False, "message": "没有正在运行的初始化"}
        _cancel_event.set()
        return {"ok": True, "message": "已请求中断，当前步骤完成后停止"}

    def status(self) -> Dict[str, Any]:
        """当前初始化状态（running + 当前步骤 + 各步进度 + 历史记录）。

        带中断自愈：状态文件标记 running 但发起进程已不在 / 心跳超时
        （服务重启、进程被杀）时，自动改判「已中断」并归档，避免页面
        永远卡在「进行中」。
        """
        state = self._read_state()
        if not state:
            return {"running": False, "record": None, "history": []}
        if state.get("running"):
            reason = self._stale_reason(state)
            if reason:
                record = state.get("record") or {}
                record["ok"] = False
                record["message"] = f"初始化已中断（{reason}）"
                record["finished_at"] = _now()
                self._write_state(record, running=False,
                                  _history=state.get("history", []))
                logger.warning(f"数据初始化状态自愈: {reason}")
                state = self._read_state() or {
                    "running": False, "record": record,
                    "history": state.get("history", []),
                }
        return state

    @staticmethod
    def _stale_reason(state: Dict[str, Any]) -> Optional[str]:
        """running 态失效判定：进程不在 → 服务重启；心跳超时 → 进程被杀。"""
        record = state.get("record") or {}
        owner_pid = record.get("pid")
        updated_at = str(record.get("updated_at") or "")
        if not owner_pid and not updated_at:
            # 旧版状态文件既无 pid 也无心跳，无法证明链路存活（如服务重启遗留）
            return "状态文件无存活凭据（服务可能已重启）"
        if owner_pid:
            try:
                os.kill(int(owner_pid), 0)
            except (OSError, ValueError):
                # 兼容不同平台与多 worker 部署：只判「发起进程已死」，
                # pid 属于其它存活 worker（gunicorn 多进程）不算中断
                return "服务已重启，原初始化链路丢失"
        if updated_at:
            try:
                last = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - last).total_seconds() > _STALE_HEARTBEAT_SECONDS:
                    return f"进度心跳超过 {_STALE_HEARTBEAT_SECONDS // 60} 分钟无更新"
            except ValueError:
                pass
        return None

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _step_done(self, job_type: str, params: Dict[str, Any],
                   tushare_range: Dict[str, str]) -> "tuple[bool, str]":
        """该步产物是否已存在（动态补齐判定）。

        文件类：目标 parquet 非空即算完成；分区类：data.parquet 分区存在
        且日期覆盖请求窗口（max 距窗口末端 ≤45 天、min 不晚于窗口起点
        +60 天）；衍生类（宽表/分区/因子）：产物存在且日期不过分陈旧。
        """
        root = self.data_dir
        window = params or tushare_range
        start = str(window.get("start_date") or "")
        end = str(window.get("end_date") or "")

        # 文件类
        file_assets = {
            "stock_basic": "stock_basic.parquet",
            "stock_company": "stock_company.parquet",
            "trade_calendar": "stock_trade_calendar.parquet",
            "wide_table_builder": "stock_business.parquet",
        }
        if job_type in file_assets:
            path = root / file_assets[job_type]
            if path.is_file() and path.stat().st_size > 0:
                return True, f"{file_assets[job_type]} 已存在"
            return False, ""

        # 日频 hive 分区类：要求覆盖请求窗口
        coverage_jobs = {
            "daily_history_by_date": "daily_history/daily",
            "daily_basic": "daily_basic/daily",
            "adj_factor": "adj_factor/daily",
            "moneyflow": "moneyflow/daily",
        }
        if job_type in coverage_jobs:
            lo, hi, n = _partition_date_range(root / coverage_jobs[job_type])
            if n == 0:
                return False, ""
            evidence = f"{n} 个分区（{lo}~{hi}）"
            if start and lo and lo > _shift(start, 60):
                return False, evidence  # 现有数据晚于窗口起点，覆盖不足
            if end and hi and hi < _shift(end, -45):
                return False, evidence  # 最新分区距窗口末端太远
            return True, evidence

        # 指数日线：无窗口，存在且不太陈旧即可
        if job_type == "index_daily":
            lo, hi, n = _partition_date_range(root / "index_daily")
            if n == 0:
                return False, ""
            if hi and hi < _shift(_today(), -45):
                return False, f"{n} 个分区（最新 {hi}）"
            return True, f"{n} 个分区（{lo}~{hi}）"

        # 股票分区重建：ts_code 分区目录已产出
        if job_type == "stock_partition_rebuild":
            stock_dir = root / "daily_history" / "stock"
            n = sum(1 for _ in stock_dir.glob("ts_code=*")) if stock_dir.is_dir() else 0
            if n > 0:
                return True, f"{n} 只标的分区"
            return False, ""

        # 财务三表（fuyao）：三表都有年份分区且最新年份不过分陈旧
        if job_type == "financial_fuyao":
            year_ends = []
            for table in ("balance_sheet", "income_statement", "cash_flow"):
                years = _year_partitions(root / table)
                if not years:
                    return False, f"{table} 无数据"
                year_ends.append(max(years))
            latest = min(year_ends)
            if latest < datetime.now().year - 1:
                return False, f"最新年份 {latest}"
            return True, f"三表齐（至 {latest} 年）"

        # 因子计算：factor_values 有近期分区
        if job_type == "factor_compute":
            lo, hi, n = _partition_date_range(root / "ml_factor_state" / "factor_values")
            if n and hi and hi >= _shift(_today(), -60):
                return True, f"{n} 个因子分区（至 {hi}）"
            return False, ""

        # 基本面 PIT：factor_values 最新分区含 PIT 因子（ocf_to_ni 等）
        if job_type == "fundamental_pit_compute":
            ok, evidence = self._pit_factors_present(root)
            return (True, evidence) if ok else (False, "")

        # 常用策略预置：清单里的策略名都已存在则跳过
        if job_type == "seed_strategies":
            names = _seeded_strategy_names()
            existing = _existing_strategy_names(root)
            if names and names <= existing:
                return True, f"{len(names)} 个预置策略已存在"
            return False, ""

        return False, ""

    @staticmethod
    def _pit_factors_present(root: Path) -> "tuple[bool, str]":
        """最新 factor_values 分区是否含 PIT 因子（读单个小分区文件）。"""
        try:
            import pandas as pd

            latest_dir = _latest_date_partition_dir(root / "ml_factor_state" / "factor_values")
            if latest_dir is None:
                return False, ""
            f = latest_dir / "data.parquet"
            if not f.is_file():
                return False, ""
            df = pd.read_parquet(f, columns=["factor_id"])
            ids = set(df["factor_id"].astype(str).unique())
            hit = ids & {"ocf_to_ni", "accrual_ratio", "roe_chg"}
            if hit:
                return True, f"最新分区含 {len(hit)} 个 PIT 因子"
        except Exception:
            logger.debug("PIT 因子存在性检查失败", exc_info=True)
        return False, ""

    def _run_plan(self, record: Dict[str, Any]) -> None:
        from app.services.data_jobs.service import DataJobService

        svc = DataJobService()
        tushare_range = _years_window(record["tushare_years"])
        financial_range = _years_window(record["financial_years"])

        ok = True
        message = ""
        for idx, step_def in enumerate(INIT_PLAN):
            if _cancel_event.is_set():
                ok = False
                message = "已被用户中断"
                break
            job_type = step_def["job_type"]
            params: Dict[str, Any] = {}
            if step_def["range"] == "tushare":
                params = {"start_date": tushare_range["start_date"], "end_date": tushare_range["end_date"]}
            elif step_def["range"] == "financial":
                params = {"start_date": financial_range["start_date"], "end_date": financial_range["end_date"]}

            step: Dict[str, Any] = {
                "index": idx,
                "job_type": job_type,
                "label": step_def["label"],
                "params": params,
                "status": "running",
                "started_at": _now(),
                "finished_at": None,
                "run_id": None,
                "progress": 0.0,
                "message": None,
            }
            record["steps"][idx] = step
            record["current_step"] = idx
            self._write_state(record, running=True)

            # 动态补齐：产物已存在则跳过该步（只补缺失部分）
            done, evidence = self._step_done(job_type, params, tushare_range)
            if done:
                step["status"] = "skipped"
                step["message"] = f"已有数据（{evidence}），跳过"
                step["finished_at"] = _now()
                logger.info(f"数据初始化 {job_type}: skipped（{evidence}）")
                self._write_state(record, running=True)
                continue

            # 常用策略预置：轻量内存操作，不走 DataJobService 子作业
            if job_type == "seed_strategies":
                try:
                    from app.services.strategy_seeds import seed_default_strategies
                    result = seed_default_strategies()
                    created, skipped = result["created"], result["skipped"]
                    if result["failed"]:
                        step["status"] = "error"
                        step["message"] = f"部分预置失败: {result['failed']}"
                        ok = False
                        message = step["message"]
                    else:
                        step["status"] = "success"
                        step["message"] = (
                            f"新建 {created}；已有跳过 {skipped}" if created
                            else "预置策略均已存在"
                        )
                except Exception as exc:  # noqa: BLE001
                    step["status"] = "error"
                    step["message"] = f"策略预置失败: {exc}"
                    ok = False
                    message = step["message"]
                step["finished_at"] = _now()
                logger.info(f"数据初始化 {job_type}: {step['status']}")
                self._write_state(record, running=True)
                if not ok:
                    break
                continue

            try:
                run = svc.submit(job_type, params)
                step["run_id"] = run.id
                final = self._wait_run(svc, run.id, step)
                if _cancel_event.is_set():
                    step["status"] = "cancelled"
                    step["message"] = "用户中断"
                    ok = False
                    message = "已被用户中断"
                else:
                    step["status"] = str(getattr(final, "status", "") or "unknown")
                    step["message"] = getattr(final, "progress_message", None)
                    if step["status"] != "success":
                        ok = False
                        message = f"{step_def['label']}（{job_type}）结束于 {step['status']}"
            except Exception as exc:
                ok = False
                message = f"{step_def['label']}（{job_type}）提交失败: {exc}"
                step["status"] = "error"
                step["message"] = message

            step["finished_at"] = _now()
            logger.info(f"数据初始化 {job_type}: {step['status']}")
            self._write_state(record, running=True)
            if not ok:
                break

        record["ok"] = ok
        record["message"] = message or "初始化完成"
        record["finished_at"] = _now()
        record["current_step"] = None if ok else record.get("current_step")
        self._write_state(record, running=False)

    def _wait_run(self, svc, run_id: int, step: Dict[str, Any],
                  timeout: float = 7200.0):
        """轮询等待作业终态，期间把 progress/message 实时刷进状态文件。"""
        deadline = time.monotonic() + timeout
        last_flush = 0.0
        while time.monotonic() < deadline:
            if _cancel_event.is_set():
                # 用户中断：立即返回当前 run（状态由调用方标记 cancelled）
                return svc.get_run(run_id)
            run = svc.get_run(run_id)
            status = str(getattr(run, "status", "") or "")
            step["progress"] = float(getattr(run, "progress", 0.0) or 0.0)
            step["message"] = getattr(run, "progress_message", None)
            if status not in ("queued", "running", "pending", ""):
                return run
            if time.monotonic() - last_flush > 2.0:
                self._write_state_running_snapshot(step)
                last_flush = time.monotonic()
            time.sleep(_POLL_INTERVAL)
        return svc.get_run(run_id)

    def _write_state_running_snapshot(self, step: Dict[str, Any]) -> None:
        """运行中单步进度刷新（只改内存中 record 引用并整体重写）。"""
        state = self._read_state()
        record = (state or {}).get("record")
        if record and isinstance(record.get("steps"), dict):
            idx = str(step.get("index"))
            if idx in record["steps"]:
                record["steps"][idx]["progress"] = step["progress"]
                record["steps"][idx]["message"] = step["message"]
                self._write_state(record, running=True, _history=state.get("history", []))

    # ------------------------------------------------------------------
    # 状态持久化（原子写，模式同 pipeline_runs.json）
    # ------------------------------------------------------------------
    def _new_record(self, tushare_years: int, financial_years: int) -> Dict[str, Any]:
        return {
            "started_at": _now(),
            "finished_at": None,
            "trigger": "manual",
            "pid": os.getpid(),
            "updated_at": _now(),
            "tushare_years": tushare_years,
            "financial_years": financial_years,
            "tushare_window": _years_window(tushare_years),
            "financial_window": _years_window(financial_years),
            "steps_total": len(INIT_PLAN),
            "current_step": None,
            "steps": {},
            "ok": False,
            "message": None,
        }

    def _read_state(self) -> Optional[Dict[str, Any]]:
        try:
            if not self.state_path.exists():
                return None
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取初始化状态文件失败", exc_info=True)
            return None

    def _write_state(self, record: Dict[str, Any], *, running: bool,
                     _history: Optional[List[Any]] = None) -> None:
        try:
            history: List[Any]
            if _history is not None:
                history = _history
            else:
                old = self._read_state() or {}
                history = old.get("history", [])
                prev = old.get("record")
                # 结束态：本次 record 归档进 history；运行态：prev 仍在跑不归档
                if prev and prev.get("finished_at") and prev is not record:
                    history = [prev] + history
                if not running and record.get("finished_at"):
                    record_snapshot = dict(record)
                    if not history or history[0].get("started_at") != record_snapshot.get("started_at"):
                        history = [record_snapshot] + history
            history = history[:_MAX_RECORDS]
            record["updated_at"] = _now()
            state = {"running": running, "record": record, "history": history}
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self.state_path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp, self.state_path)
        except Exception:
            logger.warning("写初始化状态文件失败", exc_info=True)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _shift(ymd: str, days: int) -> str:
    """YYYYMMDD 加减天数（越界/非法输入原样返回，判定侧按字符串比较失败）。"""
    try:
        d = datetime.strptime(ymd, "%Y%m%d")
        return (d + timedelta(days=days)).strftime("%Y%m%d")
    except ValueError:
        return ymd


def _date_from_path_parts(path: Path) -> Optional[str]:
    """从 hive 分区路径提取日期：完整段（trade_date=/date=/ds=YYYYMMDD）
    或 year=/month=/day= 组合。"""
    year = month = day = None
    for part in path.parts:
        if part.startswith("year="):
            year = "".join(ch for ch in part[5:] if ch.isdigit())
        elif part.startswith("month="):
            month = "".join(ch for ch in part[6:] if ch.isdigit())
        elif part.startswith("day="):
            day = "".join(ch for ch in part[4:] if ch.isdigit())
        else:
            for key in ("trade_date=", "date=", "ds="):
                if part.startswith(key):
                    digits = "".join(ch for ch in part[len(key):] if ch.isdigit())
                    if len(digits) == 8:
                        return digits
    if year and month and day and len(year) == 4:
        return f"{year}{month.zfill(2)}{day.zfill(2)}"
    return None


def _partition_date_range(root: Path) -> "tuple[Optional[str], Optional[str], int]":
    """root 下 data.parquet 分区的 (最早日期, 最晚日期, 分区数)。"""
    if not root.is_dir():
        return None, None, 0
    dates: List[str] = []
    for f in root.rglob("data.parquet"):
        d = _date_from_path_parts(f)
        if d:
            dates.append(d)
    if not dates:
        return None, None, 0
    return min(dates), max(dates), len(dates)


def _year_partitions(root: Path) -> List[int]:
    """root 下 year=YYYY 分区的年份列表。"""
    if not root.is_dir():
        return []
    years = []
    for d in root.iterdir():
        if d.is_dir() and d.name.startswith("year="):
            try:
                years.append(int(d.name[5:]))
            except ValueError:
                continue
    return years


def _seeded_strategy_names() -> set:
    """预置策略名集合（清单加载失败返回空集 = 跳过判定失败，会重跑预置）。"""
    try:
        from app.services.strategy_seeds import _seed_definitions

        return {s["name"] for s in _seed_definitions()}
    except Exception:
        logger.warning("预置策略清单加载失败", exc_info=True)
        return set()


def _existing_strategy_names(root: Path) -> set:
    """策略库中已存在的策略名（表缺失/读失败返回空集）。"""
    try:
        import pandas as pd

        path = root / "ml_factor_state" / "strategy_definitions.parquet"
        if not path.is_file():
            # 兜底：状态库 base_dir 被环境变量挪走时的根目录同名文件
            alt = root / "strategy_definitions.parquet"
            path = alt if alt.is_file() else path
        if not path.is_file():
            return set()
        df = pd.read_parquet(path, columns=["name"])
        return set(df["name"].astype(str).unique())
    except Exception:
        logger.debug("策略定义表读取失败", exc_info=True)
        return set()


def _latest_date_partition_dir(root: Path) -> Optional[Path]:
    """按路径日期取最新分区目录（与 _partition_date_range 同一日期口径）。"""
    if not root.is_dir():
        return None
    best: "tuple[Optional[str], Optional[Path]]" = (None, None)
    for f in root.rglob("data.parquet"):
        d = _date_from_path_parts(f)
        if d and (best[0] is None or d > best[0]):
            best = (d, f.parent)
    return best[1]


def _clamp_years(value: Any, default: int) -> int:
    try:
        years = int(value)
    except (TypeError, ValueError):
        years = default
    return max(1, min(years, _MAX_YEARS))


def _years_window(years: int) -> Dict[str, str]:
    """N 年窗口：start = 今天往前推 N 年，end = 今天（runner 转 env）。"""
    today = datetime.now()
    start_year = today.year - years
    start = max(start_year, 1990)
    return {
        "start_date": f"{start:04d}{today.month:02d}{today.day:02d}",
        "end_date": today.strftime("%Y%m%d"),
    }
