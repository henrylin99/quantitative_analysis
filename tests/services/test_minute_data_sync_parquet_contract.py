from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.minute_data_sync_service import MinuteDataSyncService
from app.services.minute_parquet_reader import MinuteParquetReader


def test_sync_single_stock_writes_minute_parquet(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    frame = pd.DataFrame(
        [
            {
                "ts_code": "sz.000001",
                "datetime": datetime(2026, 6, 4, 9, 31),
                "period_type": "1min",
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
                "pre_close": 9.9,
                "change": 0.2,
                "pct_chg": 2.02,
            },
            {
                "ts_code": "sz.000001",
                "datetime": datetime(2026, 6, 4, 9, 32),
                "period_type": "1min",
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "volume": 1200,
                "amount": 12240.0,
                "pre_close": 10.1,
                "change": 0.1,
                "pct_chg": 0.99,
            },
        ]
    )

    service = MinuteDataSyncService()
    with patch.object(service, "get_stock_minute_data_bs", return_value=frame):
        result = service.sync_single_stock_data("sz.000001", "1min", "2026-06-04", "2026-06-04")

    parquet_path = Path(tmp_path) / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04" / "data.parquet"
    reader = MinuteParquetReader(data_dir=str(tmp_path))
    synced = reader.get_data(ts_code="sz.000001", period_type="1min")

    assert result["success"] is True
    assert parquet_path.is_file()
    assert len(synced) == 2
    assert result["parquet_count"] == 2
    assert result["error_count"] == 0


def test_aggregate_data_reads_and_writes_minute_parquet(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    source_dir = Path(tmp_path) / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    source_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ts_code": "sz.000001",
                "period_type": "1min",
                "datetime": datetime(2026, 6, 4, 9, 31),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
            },
            {
                "ts_code": "sz.000001",
                "period_type": "1min",
                "datetime": datetime(2026, 6, 4, 9, 32),
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "volume": 1200,
                "amount": 12240.0,
            },
            {
                "ts_code": "sz.000001",
                "period_type": "1min",
                "datetime": datetime(2026, 6, 4, 9, 33),
                "open": 10.2,
                "high": 10.4,
                "low": 10.1,
                "close": 10.3,
                "volume": 1500,
                "amount": 15450.0,
            },
            {
                "ts_code": "sz.000001",
                "period_type": "1min",
                "datetime": datetime(2026, 6, 4, 9, 34),
                "open": 10.3,
                "high": 10.5,
                "low": 10.2,
                "close": 10.4,
                "volume": 1800,
                "amount": 18720.0,
            },
        ]
    ).to_parquet(source_dir / "data.parquet", index=False)

    from app.services.realtime_data_manager import RealtimeDataManager

    manager = RealtimeDataManager()
    result = manager.aggregate_data("sz.000001", source_period="1min", target_period="60min", start_date="20260604", end_date="20260604")

    target_path = Path(tmp_path) / "stock_minute" / "60min" / "year=2026" / "month=06" / "day=04" / "data.parquet"
    reader = MinuteParquetReader(data_dir=str(tmp_path))
    aggregated = reader.get_data(ts_code="sz.000001", period_type="60min")

    assert result["success"] is True
    assert target_path.is_file()
    assert len(aggregated) == 1
    assert result["parquet_count"] == 1
