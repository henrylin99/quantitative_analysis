from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Tuple

PARQUET_ASSETS = (
    "stock_basic.parquet",
    "stock_trade_calendar.parquet",
    "daily_history/daily",
    "daily_basic/daily",
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
    missing_parquet_assets = [asset for asset in PARQUET_ASSETS if asset not in existing_tables]
    empty_parquet_assets = [
        asset for asset in PARQUET_ASSETS if asset in existing_tables and asset not in non_empty_tables
    ]
    mode = str(app_config.get("DATA_JOB_EXECUTION_MODE", "celery") or "celery").lower()
    next_actions: list[str] = []

    if not connected:
        next_actions.append("Parquet 数据目录不可用，请先检查 DATA_DIR 配置和本地文件系统权限。")
    elif {"stock_trade_calendar.parquet", "stock_basic.parquet"} & set(missing_parquet_assets):
        next_actions.append("优先执行交易日历和股票基础资料下载任务，补齐基础 Parquet 资产后再执行其他日频任务。")
    elif {"stock_trade_calendar.parquet", "stock_basic.parquet"} & set(empty_parquet_assets):
        next_actions.append("优先执行交易日历和股票基础资料下载任务，当前关键 Parquet 资产仍为空。")
    elif empty_parquet_assets:
        next_actions.append("Parquet 目录结构已就绪，请按数据管理页推荐初始化顺序补齐剩余核心数据。")
    else:
        next_actions.append("基础检查通过，可直接使用数据管理页面执行日频任务或分钟数据维护。")

    return {
        "entrypoint": "run.py",
        "database": {
            "ok": bool(connected) and not missing_parquet_assets,
            "connected": bool(connected),
            "missing_tables": missing_parquet_assets,
            "empty_tables": empty_parquet_assets,
            "missing_parquet_assets": missing_parquet_assets,
            "empty_parquet_assets": empty_parquet_assets,
            "next_actions": next_actions,
        },
        "data_jobs": {
            "execution_mode": mode,
        },
    }


def inspect_parquet_data_assets(data_dir: str | None = None) -> Tuple[bool, set[str], set[str]]:
    """Inspect the Parquet assets required by the data-management page."""
    root = Path(
        data_dir
        or os.getenv(
            "DATA_DIR",
            os.path.join(os.path.dirname(__file__), "data"),
        )
    )
    if not root.exists():
        return False, set(), set()

    existing_assets: set[str] = set()
    non_empty_assets: set[str] = set()

    for asset in PARQUET_ASSETS:
        asset_path = root / asset
        if asset_path.is_file():
            existing_assets.add(asset)
            if asset_path.stat().st_size > 0:
                non_empty_assets.add(asset)
            continue

        if asset_path.is_dir():
            parquet_files = [path for path in asset_path.rglob("data.parquet") if path.is_file()]
            if parquet_files:
                existing_assets.add(asset)
                if any(path.stat().st_size > 0 for path in parquet_files):
                    non_empty_assets.add(asset)

    return True, existing_assets, non_empty_assets


def build_health_summary_lines(report: Mapping[str, object]) -> list[str]:
    database = report.get("database", {})
    data_jobs = report.get("data_jobs", {})
    missing_tables = database.get("missing_tables", [])
    empty_tables = database.get("empty_tables", [])
    next_actions = database.get("next_actions", [])

    lines = [
        "健康检查摘要:",
        f"  - 主启动入口: {report.get('entrypoint', 'run.py')}",
        f"  - Parquet 数据目录: {'正常' if database.get('connected') else '失败'}",
    ]

    if missing_tables:
        lines.append(f"  - 缺失关键资产: {', '.join(missing_tables)}")
    else:
        lines.append("  - 关键资产检查: 通过")

    if empty_tables:
        lines.append(f"  - 空资产提示: {', '.join(empty_tables)}")

    lines.append(f"  - 数据任务模式: {data_jobs.get('execution_mode', '-')}")

    if next_actions:
        lines.append("  - 推荐下一步:")
        lines.extend([f"    * {action}" for action in next_actions])

    return lines


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
