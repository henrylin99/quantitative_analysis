from __future__ import annotations

from typing import Mapping

REQUIRED_TABLES = (
    "stock_basic",
    "stock_trade_calendar",
    "data_job_run",
)


def build_health_report(
    app_config: Mapping[str, object],
    *,
    connected: bool,
    existing_tables: set[str] | None = None,
    non_empty_tables: set[str] | None = None,
) -> dict[str, object]:
    existing_tables = existing_tables or set()
    non_empty_tables = non_empty_tables or set()
    missing_tables = [table for table in REQUIRED_TABLES if table not in existing_tables]
    empty_tables = [
        table for table in REQUIRED_TABLES if table in existing_tables and table not in non_empty_tables
    ]
    mode = str(app_config.get("DATA_JOB_EXECUTION_MODE", "celery") or "celery").lower()
    next_actions: list[str] = []

    if not connected:
        next_actions.append("数据库连接失败，请先检查 .env 中的数据库配置，并确认数据库服务已经启动。")
    elif "data_job_run" in missing_tables:
        next_actions.append("缺少 data_job_run 等任务表，请先执行数据库初始化，再进入日频数据中心。")
    elif {"stock_trade_calendar", "stock_basic"} & set(missing_tables):
        next_actions.append("优先执行交易日历和股票基础资料下载任务，补齐基础依赖后再执行其他日频任务。")
    elif {"stock_trade_calendar", "stock_basic"} & set(empty_tables):
        next_actions.append("优先执行交易日历和股票基础资料下载任务，当前关键基础表仍为空。")
    elif empty_tables:
        next_actions.append("数据库结构已就绪，请按数据管理页推荐初始化顺序补齐剩余核心数据。")
    else:
        next_actions.append("基础检查通过，可直接使用数据管理页面执行日频任务或分钟数据维护。")

    return {
        "entrypoint": "run.py",
        "database": {
            "ok": bool(connected) and not missing_tables,
            "connected": bool(connected),
            "missing_tables": missing_tables,
            "empty_tables": empty_tables,
            "next_actions": next_actions,
        },
        "data_jobs": {
            "execution_mode": mode,
        },
    }


def build_startup_report(app_config: Mapping[str, object]) -> list[str]:
    mode = str(app_config.get("DATA_JOB_EXECUTION_MODE", "celery") or "celery").lower()
    lines = [
        "主启动入口: python run.py",
        "run_system.py 用于初始化与诊断，不作为日常 Web 启动入口。",
        f"DATA_JOB_EXECUTION_MODE={mode}",
    ]

    if mode == "inline":
        lines.append("日频数据中心任务将在当前 Web 进程内执行，无需单独启动 Celery worker。")
    else:
        host = app_config.get("REDIS_HOST", "localhost")
        port = app_config.get("REDIS_PORT", 6379)
        db = app_config.get("REDIS_DB", 0)
        lines.append(f"日频数据中心任务将通过 Celery 执行，请确认 Redis 可用: redis://{host}:{port}/{db}")
        lines.append("如需使用日频数据中心，请额外启动 Celery worker。")

    return lines
