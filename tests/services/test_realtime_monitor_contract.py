from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.realtime_monitor_service import RealtimeMonitorService
from app.services.data_reader import ParquetDataReader


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 4, 10, 0, 0)


def _write_parquet_assets(tmp_path: Path):
    pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "area": "深圳", "industry": "银行", "list_date": "1991-04-03"},
            {"ts_code": "000002.SZ", "symbol": "000002", "name": "万科A", "area": "深圳", "industry": "房地产", "list_date": "1991-01-29"},
        ]
    ).to_parquet(tmp_path / "stock_basic.parquet", index=False)

    minute_dir = tmp_path / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    minute_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": FixedDateTime(2026, 6, 4, 9, 31),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
            },
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": FixedDateTime(2026, 6, 4, 9, 59),
                "open": 10.1,
                "high": 10.4,
                "low": 10.0,
                "close": 10.3,
                "volume": 1500,
                "amount": 15450.0,
            },
            {
                "ts_code": "000002.SZ",
                "period_type": "1min",
                "datetime": FixedDateTime(2026, 6, 4, 9, 58),
                "open": 20.0,
                "high": 20.1,
                "low": 19.8,
                "close": 19.9,
                "volume": 2000,
                "amount": 39800.0,
            },
        ]
    ).to_parquet(minute_dir / "data.parquet", index=False)


def test_monitor_service_reads_quotes_and_overview_from_parquet(tmp_path, monkeypatch):
    _write_parquet_assets(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    ParquetDataReader._stock_basic_cache = None

    service = RealtimeMonitorService()

    with patch("app.services.realtime_monitor_service.datetime", FixedDateTime):
        quotes = service.get_realtime_quotes(stock_codes=["000001.SZ", "000002.SZ"], limit=10)
        overview = service.get_monitor_overview()

    assert quotes["success"] is True
    assert quotes["data"]["total_count"] == 2
    assert quotes["data"]["quotes"][0]["name"] in {"平安银行", "万科A"}
    assert overview["success"] is True
    assert overview["data"]["total_stocks"] == 2
    assert overview["data"]["active_stocks"] == 2
