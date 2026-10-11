"""全市场分钟线同步入口（批次 3.2）。

数据作业与晚间调度链共用：默认增量模式同步全市场 5min；回填模式把
窗口拉长到 DATA_JOB_START_DATE（缺省约 6 个月滚动窗口）。

Env 契约（数据作业参数注入，与既有作业一致）：
- DATA_JOB_PERIOD_TYPE: 5min/15min/30min/60min（默认 5min）
- DATA_JOB_MINUTE_MODE: incremental/backfill（默认 incremental）
- DATA_JOB_START_DATE: backfill 模式起点 YYYYMMDD（缺省=今天-185 天）
- DATA_JOB_LIMIT: 只同步前 N 只（调试用）

Usage:
    python app/utils/minute_market_sync.py                # 全市场增量
    DATA_JOB_MINUTE_MODE=backfill python app/utils/minute_market_sync.py
    DATA_JOB_LIMIT=5 python app/utils/minute_market_sync.py   # 小样本验证
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.services.minute_market_sync_service import MinuteMarketSyncService


def main() -> int:
    period_type = os.getenv("DATA_JOB_PERIOD_TYPE", "5min")
    mode = os.getenv("DATA_JOB_MINUTE_MODE", "incremental")
    limit = os.getenv("DATA_JOB_LIMIT")
    start_date = None
    if mode == "backfill":
        raw = os.getenv("DATA_JOB_START_DATE")
        if raw:
            start_date = raw.replace("-", "")
        else:
            start_date = (datetime.now() - timedelta(days=185)).strftime("%Y%m%d")

    service = MinuteMarketSyncService()
    stock_list = None
    if limit:
        universe = service.load_stock_universe()
        stock_list = universe[: int(limit)]

    result = service.sync_market(
        period_type=period_type,
        mode=mode,
        start_date=start_date,
        stock_list=stock_list,
    )
    print(f"[minute_market_sync] {result['message']}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
