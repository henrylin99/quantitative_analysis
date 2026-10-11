"""基本面 PIT 因子数据作业：单日（晚间链路）/区间（回填）两种模式。

环境变量（与其他数据作业一致）：
- DATA_JOB_TRADE_DATE：单日模式
- DATA_JOB_START_DATE / DATA_JOB_END_DATE：区间回填（只落交易日）
- 两者都不传：默认最新交易日
"""

import os
import sys
from pathlib import Path

# 兼容直接运行（python app/utils/fundamental_pit_compute.py）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_PROJECT_ROOT), str(_PROJECT_ROOT / "app" / "utils")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from parquet_job_helpers import normalize_ymd  # noqa: E402

from app.services.fundamental_pit_service import FundamentalPitService  # noqa: E402


def main():
    service = FundamentalPitService()
    trade_date = normalize_ymd(os.getenv("DATA_JOB_TRADE_DATE"))
    start = normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end = normalize_ymd(os.getenv("DATA_JOB_END_DATE"))

    if start or end:
        today = __import__("datetime").datetime.now().strftime("%Y%m%d")
        result = service.compute_range(start or end, end or start or today)
    else:
        if not trade_date:
            from app.utils.parquet_job_helpers import available_open_trade_dates

            days = available_open_trade_dates()
            trade_date = days[-1] if days else None
        if not trade_date:
            print("[fund_pit_compute] 无可用交易日（交易日历为空）")
            sys.exit(1)
        result = service.compute_and_save(trade_date)

    print(f"[fund_pit_compute] {result}")
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
