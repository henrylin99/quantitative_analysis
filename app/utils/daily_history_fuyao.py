"""扶摇全市场日线行情下载（daily_history/daily 表的 fuyao 生产者）。

与 tushare 版（daily_history_by_date.py / daily_history_by_code.py）写入同一张
Parquet 表、同一套 schema，两者是同表的可选生产者，读取侧无感知。

取数走 FuyaoDailyFetcher 三档策略（近端 10d dump → 10 年 dump → 单标的兜底），
见 app/utils/data_sources/fuyao_dump.py；单位/时区换算集中在 fuyao_normalize。

前置依赖：trade_calendar（交易日解析）。冷启动可用显式参数：
    DATA_JOB_TRADE_DATE=20260904 python app/utils/daily_history_fuyao.py
"""

import sys
from pathlib import Path

# 兼容直接运行（python app/utils/daily_history_fuyao.py）：
# 此时 sys.path[0] 是 app/utils，需要把项目根加进去才能 import app.*
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.data_sources.fuyao_dump import FuyaoDailyFetcher
from app.utils.parquet_job_helpers import resolve_trade_dates_with_gap_fill
from app.utils.parquet_writer import save_to_parquet

REL_TABLE = "daily_history/daily"


def main() -> int:
    trade_dates, _ = resolve_trade_dates_with_gap_fill(REL_TABLE)
    if not trade_dates:
        print("[daily_history_fuyao] 没有需要拉取的交易日")
        return 0

    fetcher = FuyaoDailyFetcher()
    frames = fetcher.fetch_dates(trade_dates)

    total = 0
    failed = []
    for trade_date in trade_dates:
        frame = frames.get(trade_date)
        if frame is None or frame.empty:
            failed.append(trade_date)
            continue
        total += save_to_parquet(frame, trade_date, REL_TABLE)

    saved_days = len(trade_dates) - len(failed)
    print(
        f"[daily_history_fuyao] 完成，trade_days={len(trade_dates)}, "
        f"saved_days={saved_days}, total_upsert={total}"
    )
    if failed:
        print(f"[daily_history_fuyao] 以下交易日未取得数据（作业标记失败，可重试）: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
