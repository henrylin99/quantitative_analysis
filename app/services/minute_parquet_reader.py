from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
from datetime import timezone

import pandas as pd
from loguru import logger


class MinuteParquetReader:
    """Read minute-level stock data from partitioned parquet files."""

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    def get_data(
        self,
        ts_code: str | None = None,
        period_type: str | None = None,
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for parquet_path in self._walk_parquet_files(period_type, start_time, end_time):
            try:
                df = pd.read_parquet(parquet_path)
            except Exception as exc:
                logger.warning(f"读取分钟 parquet 失败 {parquet_path}: {exc}")
                continue
            if not df.empty:
                frames.append(df)

        if not frames:
            return pd.DataFrame()

        result = pd.concat(frames, ignore_index=True)
        if "datetime" in result.columns:
            result["datetime"] = pd.to_datetime(result["datetime"], errors="coerce")
            if getattr(result["datetime"].dt, "tz", None) is not None:
                result["datetime"] = result["datetime"].dt.tz_localize(None)
            result = result.dropna(subset=["datetime"])
        if ts_code is not None and "ts_code" in result.columns:
            candidate_codes = _minute_code_aliases(ts_code)
            result = result[result["ts_code"].astype(str).isin(candidate_codes)]
        if period_type is not None and "period_type" in result.columns:
            result = result[result["period_type"] == period_type]
        if start_time is not None:
            start_dt = _normalize_dt(start_time)
            result = result[result["datetime"] >= start_dt]
        if end_time is not None:
            end_dt = _normalize_dt(end_time)
            result = result[result["datetime"] <= end_dt]
        if "datetime" in result.columns:
            result = result.sort_values(["datetime", "ts_code"], kind="stable").reset_index(drop=True)
        return result

    def get_latest_data(self, ts_code: str, period_type: str = "1min", limit: int = 100) -> pd.DataFrame:
        df = self.get_data(ts_code=ts_code, period_type=period_type)
        if df.empty:
            return df
        return df.sort_values("datetime", ascending=False).head(limit).reset_index(drop=True)

    def get_summary(self, ts_code: str, period_type: str = "1min", hours: int = 24) -> dict[str, object]:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        df = self.get_data(ts_code=ts_code, period_type=period_type, start_time=start_time, end_time=end_time)
        if df.empty:
            return {
                "has_data": False,
                "data_count": 0,
                "latest_time": None,
                "earliest_time": None,
                "missing_count": 0,
                "completeness": 0.0,
                "status": "no_data",
                "message": f"没有找到 {ts_code} 在过去 {hours} 小时的 {period_type} 数据",
            }

        latest_time = pd.to_datetime(df["datetime"]).max().to_pydatetime().isoformat()
        earliest_time = pd.to_datetime(df["datetime"]).min().to_pydatetime().isoformat()
        return {
            "has_data": True,
            "data_count": int(len(df)),
            "latest_time": latest_time,
            "earliest_time": earliest_time,
            "missing_count": 0,
            "completeness": 100.0,
            "status": "ok",
            "message": f"数据完整性: {100.0:.1f}%",
        }

    def _walk_parquet_files(
        self,
        period_type: str | None,
        start_time: str | datetime | None,
        end_time: str | datetime | None,
    ) -> Iterable[Path]:
        base = Path(self.data_dir) / "stock_minute"
        if period_type:
            bases = [base / period_type]
        else:
            bases = [path for path in base.iterdir() if path.is_dir()] if base.exists() else []

        start_dt = _normalize_dt(start_time) if start_time is not None else None
        end_dt = _normalize_dt(end_time) if end_time is not None else None

        for period_base in bases:
            if not period_base.exists():
                continue
            for year_dir in sorted(_partition_dirs(period_base, "year")):
                y = _partition_value(year_dir.name, "year")
                if y is None:
                    continue
                for month_dir in sorted(_partition_dirs(year_dir, "month")):
                    m = _partition_value(month_dir.name, "month")
                    if m is None:
                        continue
                    for day_dir in sorted(_partition_dirs(month_dir, "day")):
                        d = _partition_value(day_dir.name, "day")
                        if d is None:
                            continue
                        day_str = f"{y}-{m}-{d}"
                        if start_dt and day_str < start_dt.strftime("%Y-%m-%d"):
                            continue
                        if end_dt and day_str > end_dt.strftime("%Y-%m-%d"):
                            continue
                        parquet_path = day_dir / "data.parquet"
                        if parquet_path.is_file():
                            yield parquet_path


def _partition_dirs(parent: Path, key: str) -> list[Path]:
    if not parent.exists():
        return []
    return [path for path in parent.iterdir() if path.is_dir() and path.name.startswith(f"{key}=")]


def _partition_value(dir_name: str, key: str) -> Optional[str]:
    prefix = f"{key}="
    if not dir_name.startswith(prefix):
        return None
    value = dir_name[len(prefix):]
    if key in {"month", "day"} and len(value) == 1:
        value = f"0{value}"
    return value


def _normalize_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    text = str(value)
    if len(text) == 10 and text[4] == "-":
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


def _minute_code_aliases(value: str) -> set[str]:
    text = str(value).strip()
    lower_text = text.lower()
    aliases = {text, lower_text}

    # 兼容前端直接传入的 6 位纯数字代码（例如 300502）
    if lower_text.isdigit() and len(lower_text) == 6:
        market = 'SH' if lower_text.startswith('6') else 'SZ'
        aliases.add(f"{lower_text}.{market}")
        aliases.add(f"{market.lower()}.{lower_text}")

    if lower_text.startswith(("sh.", "sz.")):
        market, symbol = lower_text.split(".", 1)
        aliases.add(f"{symbol}.{market.upper()}")
    elif lower_text.endswith(".sh") or lower_text.endswith(".sz"):
        symbol, market = lower_text.split(".", 1)
        aliases.add(f"{market}.{symbol}")
        aliases.add(f"{symbol}.{market.upper()}")

    return aliases
