"""
Parquet 分区写入工具。

将 DataFrame 按 Hive 分区格式写入本地文件系统：
    {data_dir}/{table}/year=YYYY/month=MM/day=DD/data.parquet
"""

import os
from typing import Optional

import pandas as pd
from loguru import logger


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

    if data_dir is None:
        data_dir = os.getenv(
            "DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
        )

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
    df.to_parquet(parquet_path, index=False, engine="pyarrow")

    logger.info(f"写入 parquet: {parquet_path} ({len(df)} 行)")
    return len(df)
