"""股票分区重建作业
从日期分区（daily/year=/month=/day=）重建各日频表的按股票分区
（stock/ts_code=XXX/data.parquet）。重建后按 ts_code 的个股查询
优先走股票分区，单股历史只读一个文件而不是全市场日分区。

Usage:
    python app/utils/stock_partition_rebuild.py

Registered as a derived job in DataJobService。
建议放在日频下载作业（daily_history / daily_basic / stk_factor /
moneyflow / cyq_perf）之后运行，保持股票分区与最新数据同步；
落后时查询会自动回退日期分区，结果不变只是变慢。

参数（与数据管理页面 / AI run_data_job 的通用参数一致，由 runner 转
成环境变量）：
- DATA_JOB_START_DATE / DATA_JOB_END_DATE：只增量合并窗口内的交易日
  （与下载作业传同一窗口即可）；股票分区尚不存在时自动转全量重建
- DATA_JOB_FULL_REFRESH：真值时忽略窗口，强制全量重建
- STOCK_REBUILD_WORKERS：并行线程数，默认 16
"""

import sys
import os

# 支持两种运行方式：
# 1. 作为 data_jobs 子进程（PYTHONPATH 已含项目根目录）
# 2. 从 Flask app context 直接 import
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.utils.parquet_job_helpers import env_bool, normalize_ymd
from app.utils.stock_partition import rebuild_all_tables


def main() -> int:
    try:
        workers = int(os.getenv("STOCK_REBUILD_WORKERS", "16"))
    except ValueError:
        workers = 16

    start_date = normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end_date = normalize_ymd(os.getenv("DATA_JOB_END_DATE"))
    if env_bool("DATA_JOB_FULL_REFRESH", default=False):
        start_date = end_date = None
        print("[stock_partition_rebuild] FULL_REFRESH：忽略日期窗口，执行全量重建")
    elif start_date or end_date:
        print(f"[stock_partition_rebuild] 窗口增量合并: {start_date or '最早'} ~ {end_date or '最新'}")

    results = rebuild_all_tables(
        max_workers=workers,
        start_date=start_date,
        end_date=end_date,
    )
    skipped = [r for r in results if r.get("mode") == "skipped"]
    failed = [r for r in results if r.get("mode") == "failed"]
    for stats in skipped:
        print(f"[stock_partition_rebuild] {stats['table']} 跳过（日期分区为空）")
    if failed:
        for stats in failed:
            print(f"[stock_partition_rebuild] {stats['table']} 失败: {stats.get('error')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
