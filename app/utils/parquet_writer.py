"""
Parquet 分区写入工具。

将 DataFrame 按 Hive 分区格式写入本地文件系统：
    {data_dir}/{table}/year=YYYY/month=MM/day=DD/data.parquet
"""

import os
from typing import Optional

import pandas as pd
from loguru import logger


def _data_root(data_dir: Optional[str]) -> str:
    if data_dir is None:
        return os.getenv(
            "DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
        )
    return data_dir


def atomic_write_parquet(df: pd.DataFrame, path: str) -> None:
    """原子写入：先写临时文件再 rename。

    直接 to_parquet 到最终路径时，进程被杀/磁盘满会留下半个 parquet，
    所有下游读取（data_reader 遇坏文件只 warning + 空表）会静默把
    这一天的数据当成不存在。rename 在同一文件系统上是原子的，
    读方要么看到旧文件要么看到完整新文件。
    """
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        df.to_parquet(tmp_path, index=False, engine="pyarrow")
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def save_to_parquet(
    df: pd.DataFrame,
    trade_date: str,
    table: str,
    data_dir: Optional[str] = None,
) -> int:
    """将一天的 DataFrame 写入 Hive 分区格式的 parquet 文件。

    Parameters
    ----------
    df : pd.DataFrame
        当天全市场数据，必须包含 trade_date 列。
    trade_date : str
        交易日期，支持 "YYYYMMDD" 或 "YYYY-MM-DD" 格式。
    table : str
        表名，对应子目录，如 "daily_history/daily" 或 "daily_basic/daily"。
    data_dir : str | None
        数据根目录，默认从 env DATA_DIR 读取或使用项目 data/ 目录。

    Returns
    -------
    int
        写入的行数。
    """
    if df is None or df.empty:
        return 0

    data_dir = _data_root(data_dir)

    # 统一日期格式为 YYYY, MM, DD
    clean = trade_date.replace("-", "")
    if len(clean) != 8 or not clean.isdigit():
        logger.warning(f"无效的 trade_date 格式: {trade_date}")
        return 0

    year = clean[:4]
    month = clean[4:6]
    day = clean[6:8]

    partition_dir = os.path.join(data_dir, table, f"year={year}", f"month={month}", f"day={day}")
    os.makedirs(partition_dir, exist_ok=True)

    parquet_path = os.path.join(partition_dir, "data.parquet")

    df = df.copy()
    atomic_write_parquet(df, parquet_path)

    logger.info(f"写入 parquet: {parquet_path} ({len(df)} 行)")
    return len(df)


def save_single_parquet(
    df: pd.DataFrame,
    filename: str,
    data_dir: Optional[str] = None,
) -> int:
    """将 DataFrame 写入单文件 Parquet。"""
    if df is None or df.empty:
        return 0

    data_dir = _data_root(data_dir)

    path = os.path.join(data_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = df.copy()
    atomic_write_parquet(df, path)
    logger.info(f"写入 parquet: {path} ({len(df)} 行)")
    return len(df)


def save_partitioned_parquet(
    df: pd.DataFrame,
    date_col: str,
    table: str,
    data_dir: Optional[str] = None,
) -> int:
    """按日期列分组后写入 Hive 分区格式的 parquet 文件。"""
    if df is None or df.empty or date_col not in df.columns:
        return 0

    frame = df.copy()
    frame[date_col] = pd.to_datetime(frame[date_col]).dt.strftime("%Y-%m-%d")
    total = 0
    for date_value, group in frame.groupby(date_col, sort=True):
        total += save_to_parquet(group, date_value, table, data_dir=data_dir)
    return total
