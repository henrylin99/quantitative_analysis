#!/usr/bin/env python3
"""股票分区重建脚本 —— 从日期分区重建按股票分区（查询提速用）。

用法（与 20260213 demo 同名脚本一致）：
    python rebuild_stock_partitions.py daily_history --workers 32
    python rebuild_stock_partitions.py daily_basic --workers 32
    python rebuild_stock_partitions.py moneyflow --workers 32
    python rebuild_stock_partitions.py cyq_perf --workers 32
    python rebuild_stock_partitions.py adj_factor --workers 32   # 即 stk_factor
    python rebuild_stock_partitions.py            # 重建全部表
    python rebuild_stock_partitions.py stk_factor --start-date 2026-09-01 --end-date 2026-09-22

说明：
- adj_factor 在本项目不是独立表，而是 stk_factor 表的字段，别名自动解析。
- 不给日期窗口时走全量重建（stock_staging 换名替换，失败自动恢复）；
  给定窗口时走增量合并，只刷新窗口内的交易日。
- 重建后按 ts_code 的个股查询会优先命中 stock/ts_code=XXX/data.parquet。
"""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="股票分区重建脚本")
    parser.add_argument("table_name", nargs="?", help="表名（不指定则重建所有表）")
    parser.add_argument("--start-date", help="开始日期，格式 2024-01-01 或 20240101")
    parser.add_argument("--end-date", help="结束日期，格式 2026-09-23 或 20260923")
    parser.add_argument("--workers", type=int, default=16, help="并行线程数（默认16）")
    args = parser.parse_args()

    from app.utils.stock_partition import rebuild_all_tables, resolve_table_name

    if args.table_name:
        table_name = resolve_table_name(args.table_name)
        results = rebuild_all_tables(
            max_workers=args.workers, table_names=[table_name]
        )
        return 0 if results[0].get("mode") != "failed" else 1

    results = rebuild_all_tables(max_workers=args.workers)
    failed = [r for r in results if r.get("mode") == "failed"]
    for stats in results:
        if "error" in stats:
            print(f"[stock_rebuild:{stats['table']}] 失败: {stats['error']}")
    print(f"[stock_rebuild] 全部完成: {len(results) - len(failed)}/{len(results)} 张表成功")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
