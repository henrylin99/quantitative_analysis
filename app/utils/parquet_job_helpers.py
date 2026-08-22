import os
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from app.services.data_reader import ParquetDataReader


def normalize_ymd(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    text = str(date_str).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return text
    return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_stock_codes() -> List[str]:
    reader = ParquetDataReader()
    df = reader.get_stock_basic()
    if df.empty or "ts_code" not in df.columns:
        return []
    return df["ts_code"].dropna().astype(str).tolist()


def resolve_trade_dates(default_latest_only: bool = True) -> Tuple[List[str], bool]:
    """Resolve trading dates using env vars and parquet trade calendar."""
    start_date = normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end_date = normalize_ymd(os.getenv("DATA_JOB_END_DATE"))
    trade_date = normalize_ymd(os.getenv("DATA_JOB_TRADE_DATE"))
    full_refresh = env_bool("DATA_JOB_FULL_REFRESH", default=False)

    if trade_date:
        return [trade_date], full_refresh

    reader = ParquetDataReader()
    calendar_df = reader.get_trade_calendar()
    available: List[str] = []
    if not calendar_df.empty and {"cal_date", "is_open"}.issubset(calendar_df.columns):
        work_df = calendar_df.copy()
        work_df["cal_date"] = pd.to_datetime(work_df["cal_date"], errors="coerce")
        work_df = work_df.dropna(subset=["cal_date"])
        work_df["is_open"] = pd.to_numeric(work_df["is_open"], errors="coerce").fillna(0).astype(int)
        available = (
            work_df.loc[work_df["is_open"] == 1, "cal_date"]
            .dt.strftime("%Y%m%d")
            .drop_duplicates()
            .sort_values()
            .tolist()
        )

    if not available:
        if start_date and end_date and start_date <= end_date:
            if default_latest_only:
                return [end_date], full_refresh
            return [start_date], full_refresh
        return [], full_refresh

    if not end_date:
        end_date = available[-1]

    if not start_date:
        start_date = end_date if default_latest_only else available[0]

    dates = [d for d in available if start_date <= d <= end_date]
    return dates, full_refresh


def _default_data_root() -> str:
    """与 parquet_writer.save_to_parquet 一致的数据根目录解析。"""
    return os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )


def latest_partition_date(rel_table: str, data_dir: Optional[str] = None) -> Optional[str]:
    """扫描 Hive 分区目录，返回某数据集的最新分区日期（YYYYMMDD）。

    rel_table 形如 "daily_history/daily" 或 "income_statement"。
    """
    from pathlib import Path
    import re

    root = Path(data_dir) if data_dir else Path(_default_data_root())
    table_dir = root / rel_table
    if not table_dir.exists():
        return None
    dates = []
    for match in table_dir.rglob("day=*"):
        found = re.search(r"year=(\d{4}).*month=(\d{2}).*day=(\d{2})", str(match))
        if found:
            dates.append("".join(found.groups()))
    return max(dates) if dates else None
