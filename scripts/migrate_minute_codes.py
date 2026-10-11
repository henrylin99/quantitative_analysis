"""分钟数据代码风格迁移：存量分区 sz.000001 → 000001.SZ（tushare 规范）。

背景：分钟线历史由 Baostock / 通达信链路写入，ts_code 为 ``sz.000001``
风格；2026-10 起存储规范统一为 tushare 风格（与全项目其余数据一致），
写侧已在 MinuteParquetStore 归一，本脚本负责一次性改写存量分区。

处理口径：
- 只改写 ts_code 列（normalize_minute_code），其余列不动；
- 归一后按 (ts_code, datetime, period_type) 去重 keep=last——同一根 bar
  以两种风格各存一份的（如手工补数）会合并；
- 内容无变化的分区直接跳过，幂等可重跑；
- 默认 dry-run，--execute 才落盘；逐文件走分区锁 + 原子写。

Usage:
    python scripts/migrate_minute_codes.py                 # 预览
    python scripts/migrate_minute_codes.py --execute       # 执行
    python scripts/migrate_minute_codes.py --timeframe 5min
"""
import argparse
import logging
import sys

from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")

from app.services.minute_code_style import is_tushare_style, normalize_minute_code
from app.utils.parquet_writer import atomic_write_parquet, parquet_file_lock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_minute_codes")


def find_partitions(data_dir: Path, timeframe: str | None = None) -> list[Path]:
    base = data_dir / "stock_minute"
    period_bases = [base / timeframe] if timeframe else (
        [p for p in base.iterdir() if p.is_dir()] if base.exists() else []
    )
    paths: list[Path] = []
    for period_base in sorted(period_bases):
        for parquet_path in sorted(period_base.glob("year=*/*=*/*=*/data.parquet")):
            paths.append(parquet_path)
    return paths


def migrate_partition(parquet_path: Path) -> tuple[int, int]:
    """迁移单个分区，返回 (迁移行数, 去重删除行数)；未落盘返回 (0, 0)。"""
    df = pd.read_parquet(parquet_path)
    if df.empty or "ts_code" not in df.columns:
        return 0, 0

    original_codes = df["ts_code"].astype(str)
    migrated = original_codes.map(normalize_minute_code)
    rows_changed = int((original_codes != migrated).sum())

    result = df.copy()
    result["ts_code"] = migrated
    dedup_keys = [k for k in ("ts_code", "datetime", "period_type") if k in result.columns]
    before = len(result)
    if dedup_keys:
        result = result.drop_duplicates(subset=dedup_keys, keep="last")
    rows_dropped = before - len(result)

    if rows_changed == 0 and rows_dropped == 0:
        return 0, 0

    if rows_changed:
        result = result.sort_values(
            [c for c in ("ts_code", "datetime") if c in result.columns], kind="stable"
        ).reset_index(drop=True)

    lock_path = parquet_path.with_name(f"{parquet_path.name}.lock")
    with parquet_file_lock(lock_path):
        atomic_write_parquet(result, str(parquet_path))
    logger.info(f"已迁移 {parquet_path}: 改写 {rows_changed} 行, 去重删除 {rows_dropped} 行")
    return rows_changed, rows_dropped


def main() -> int:
    parser = argparse.ArgumentParser(description="分钟数据 ts_code 风格迁移（bs 风格 → tushare 风格）")
    parser.add_argument("--data-dir", default="data", help="数据根目录（默认 data）")
    parser.add_argument("--timeframe", default=None, help="只处理指定周期（如 5min），默认全部")
    parser.add_argument("--execute", action="store_true", help="实际写盘（默认 dry-run）")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    partitions = find_partitions(data_dir, args.timeframe)
    logger.info(f"共发现 {len(partitions)} 个分钟分区（{'执行' if args.execute else 'dry-run'}）")

    total_changed = total_dropped = total_scanned = files_touched = 0
    for parquet_path in partitions:
        try:
            df = pd.read_parquet(parquet_path, columns=["ts_code"])
        except Exception as exc:  # noqa: BLE001
            logger.error(f"读取失败，跳过 {parquet_path}: {exc}")
            continue
        total_scanned += len(df)
        needs_change = (~df["ts_code"].astype(str).map(is_tushare_style)).any()
        if not needs_change and not args.execute:
            continue
        if not args.execute:
            pending = int((~df["ts_code"].astype(str).map(is_tushare_style)).sum())
            logger.info(f"[dry-run] 待迁移 {parquet_path}: {pending}/{len(df)} 行为旧风格")
            files_touched += 1
            total_changed += pending
            continue
        changed, dropped = migrate_partition(parquet_path)
        total_changed += changed
        total_dropped += dropped
        if changed or dropped:
            files_touched += 1

    logger.info(
        f"完成：扫描 {len(partitions)} 个分区 / {total_scanned} 行，"
        f"{'将迁移' if not args.execute else '已迁移'} {total_changed} 行（{files_touched} 个文件）"
        + (f"，去重删除 {total_dropped} 行" if args.execute else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
