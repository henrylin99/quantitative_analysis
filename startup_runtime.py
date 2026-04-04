from __future__ import annotations

from typing import Mapping


def build_startup_report(app_config: Mapping[str, object]) -> list[str]:
    mode = str(app_config.get("DATA_JOB_EXECUTION_MODE", "celery") or "celery").lower()
    lines = [f"DATA_JOB_EXECUTION_MODE={mode}"]

    if mode == "inline":
        lines.append("日频数据中心任务将在当前 Web 进程内执行，无需单独启动 Celery worker。")
    else:
        host = app_config.get("REDIS_HOST", "localhost")
        port = app_config.get("REDIS_PORT", 6379)
        db = app_config.get("REDIS_DB", 0)
        lines.append(f"日频数据中心任务将通过 Celery 执行，请确认 Redis 可用: redis://{host}:{port}/{db}")
        lines.append("如需使用日频数据中心，请额外启动 Celery worker。")

    return lines
