from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger


class MinuteParquetStore:
    """Persist minute-level rows to partitioned parquet files."""

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    def write_frame(self, frame: pd.DataFrame, period_type: str) -> int:
        if frame is None or frame.empty:
            return 0

        if "datetime" not in frame.columns:
            raise ValueError("minute parquet frame requires datetime column")

        df = frame.copy()
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])
        if df.empty:
            return 0

        if "period_type" not in df.columns:
            df["period_type"] = period_type

        total_rows = 0
        for date_value, day_df in df.groupby(df["datetime"].dt.date):
            total_rows += self._write_day_frame(day_df, date_value)
        return total_rows

    def _write_day_frame(self, day_df: pd.DataFrame, date_value) -> int:
        year = f"{date_value.year:04d}"
        month = f"{date_value.month:02d}"
        day = f"{date_value.day:02d}"

        partition_dir = Path(self.data_dir) / "stock_minute" / str(day_df.iloc[0]["period_type"]) / f"year={year}" / f"month={month}" / f"day={day}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = partition_dir / "data.parquet"

        if parquet_path.is_file():
            try:
                existing = pd.read_parquet(parquet_path)
            except Exception as exc:
                logger.warning(f"读取既有分钟 parquet 失败 {parquet_path}: {exc}")
                existing = pd.DataFrame()
            combined = pd.concat([existing, day_df], ignore_index=True)
        else:
            combined = day_df.copy()

        if "datetime" in combined.columns:
            combined["datetime"] = pd.to_datetime(combined["datetime"], errors="coerce")
        dedup_keys = [key for key in ["ts_code", "datetime", "period_type"] if key in combined.columns]
        if dedup_keys:
            combined = combined.drop_duplicates(subset=dedup_keys, keep="last")
        combined = combined.sort_values([col for col in ["ts_code", "datetime"] if col in combined.columns]).reset_index(drop=True)
        combined.to_parquet(parquet_path, index=False, engine="pyarrow")
        logger.info(f"写入分钟 parquet: {parquet_path} ({len(combined)} 行)")
        return len(combined)
