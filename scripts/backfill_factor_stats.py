"""factor_values 截面标准化列（percentile_rank / z_score）历史回填。

背景：历史上 alpha191 因子入库时未计算截面标准化列，导致
factor_values 里 alpha_0xx 的 percentile_rank / z_score 全为 NaN，
而打分链（stock_scoring）优先消费 z_score——这些因子实际进不了
打分体系。根因已在 Alpha191FactorService._to_long 源头修复，
本脚本负责补齐存量分区。

口径与 FactorEngine._calculate_factor_stats 一致：
- 按 (factor_id, trade_date) 截面：percentile_rank = 截面百分位×100，
  z_score = (值-均值)/标准差（零方差截面记 0）；
- 只补缺失行（factor_value 非空且标准化列为 NaN），已有值不覆盖；
- 幂等：全部补齐的分区直接跳过，可安全断点重跑。

Usage:
    python scripts/backfill_factor_stats.py                    # 全部分区
    python scripts/backfill_factor_stats.py --start 2024-01-01 --end 2024-06-30
    python scripts/backfill_factor_stats.py --dry-run
"""
import sys
import argparse
import logging

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def backfill_partition(store, table: str, partition: str,
                       dry_run: bool = False) -> tuple:
    """回填单个分区。返回 (补齐行数, 跳过原因或 None)。"""
    existing = store.read_partition(table, "trade_date", partition)
    if existing.empty:
        return 0, "空分区"

    missing_mask = (
        existing["factor_value"].notna()
        & (existing.get("percentile_rank", pd.Series(dtype=float)).isna()
           | existing.get("z_score", pd.Series(dtype=float)).isna())
    ) if "percentile_rank" in existing.columns else existing["factor_value"].notna()
    if not missing_mask.any():
        return 0, "已完整"

    df = existing.copy()
    for column in ("percentile_rank", "z_score"):
        if column not in df.columns:
            df[column] = np.nan

    sub = df.loc[missing_mask]
    grouped = sub.groupby("factor_id")["factor_value"]
    ranks = grouped.rank(pct=True) * 100
    std = grouped.transform("std")
    mean = grouped.transform("mean")
    zscores = np.where(
        std.fillna(0) > 0,
        (sub["factor_value"] - mean) / std.replace(0, np.nan),
        0.0,
    )
    df.loc[missing_mask, "percentile_rank"] = ranks.astype("float32").values
    df.loc[missing_mask, "z_score"] = pd.Series(zscores).astype("float32").values

    if not dry_run:
        with store.locked(table):
            store.write_partition(table, "trade_date", partition, df)
    return int(missing_mask.sum()), None


def main():
    from app.services.parquet_state_store import FactorRepository, ParquetStateStore

    parser = argparse.ArgumentParser(description="回填 factor_values 截面标准化列")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="只统计缺失量不写回")
    args = parser.parse_args()

    store = ParquetStateStore()
    table = FactorRepository.TABLE_VALUES
    partitions = sorted(store.list_partitions(table, "trade_date"))
    if args.start:
        partitions = [p for p in partitions if p >= args.start]
    if args.end:
        partitions = [p for p in partitions if p <= args.end]
    log.info(f"待扫描分区 {len(partitions)} 个"
             f"（{partitions[0] if partitions else '-'} ~ "
             f"{partitions[-1] if partitions else '-'}）")

    total_rows = 0
    filled = 0
    for i, partition in enumerate(partitions, 1):
        try:
            rows, reason = backfill_partition(store, table, partition,
                                              dry_run=args.dry_run)
        except Exception as exc:
            log.error(f"[{i}/{len(partitions)}] {partition} 回填失败: {exc}")
            continue
        total_rows += rows
        if rows == 0:
            continue
        filled += 1
        if args.dry_run:
            log.info(f"[{i}/{len(partitions)}] {partition} 缺失 {rows} 行（dry-run 不写回）")
        elif i % 20 == 0 or i == len(partitions):
            log.info(f"[{i}/{len(partitions)}] 进度：已回填 {filled} 个分区、{total_rows} 行")

    action = "统计完成（dry-run）" if args.dry_run else "回填完成"
    log.info(f"{action}：{filled} 个分区共 {total_rows} 行补齐标准化列")


if __name__ == "__main__":
    main()
