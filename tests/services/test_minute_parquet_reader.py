from pathlib import Path

import pandas as pd

from app.services.minute_parquet_reader import MinuteParquetReader


def test_minute_reader_loads_rows_by_stock_period_and_time_range(tmp_path):
    base = tmp_path / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    base.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {"ts_code": "sz.000001", "period_type": "1min", "datetime": "2026-06-04T09:31:00", "open": 10.0, "close": 10.1},
            {"ts_code": "sz.000001", "period_type": "1min", "datetime": "2026-06-04T09:32:00", "open": 10.1, "close": 10.2},
            {"ts_code": "sz.000002", "period_type": "1min", "datetime": "2026-06-04T09:31:00", "open": 20.0, "close": 20.1},
        ]
    )
    frame.to_parquet(base / "data.parquet", index=False)

    reader = MinuteParquetReader(data_dir=str(tmp_path))
    data = reader.get_data(ts_code="000001.SZ", period_type="1min", start_time="2026-06-04T09:31:30", end_time="2026-06-04T09:32:30")

    assert list(data["ts_code"]) == ["sz.000001"]
    assert list(data["close"]) == [10.2]
    assert data.iloc[0]["datetime"].isoformat() == "2026-06-04T09:32:00"


def test_minute_reader_returns_summary_for_latest_window(tmp_path):
    base = tmp_path / "stock_minute" / "5min" / "year=2026" / "month=06" / "day=04"
    base.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {"ts_code": "sh.600000", "period_type": "5min", "datetime": "2026-06-04T09:35:00", "open": 10.0, "close": 10.1},
            {"ts_code": "sh.600000", "period_type": "5min", "datetime": "2026-06-04T09:40:00", "open": 10.1, "close": 10.3},
        ]
    )
    frame.to_parquet(base / "data.parquet", index=False)

    reader = MinuteParquetReader(data_dir=str(tmp_path))
    summary = reader.get_summary(ts_code="600000.SH", period_type="5min", hours=24)

    assert summary["has_data"] is True
    assert summary["data_count"] == 2
    assert summary["latest_time"] == "2026-06-04T09:40:00"
    assert summary["earliest_time"] == "2026-06-04T09:35:00"
