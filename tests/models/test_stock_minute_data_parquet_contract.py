from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from app.models.stock_minute_data import StockMinuteData


def test_stock_minute_data_reads_parquet_for_six_digit_code(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    now = datetime.now().replace(second=0, microsecond=0)
    minute_dir_1m = Path(tmp_path) / "stock_minute" / "1min" / f"year={now.year:04d}" / f"month={now.month:02d}" / f"day={now.day:02d}"
    minute_dir_15m = Path(tmp_path) / "stock_minute" / "15min" / f"year={now.year:04d}" / f"month={now.month:02d}" / f"day={now.day:02d}"
    minute_dir_1m.mkdir(parents=True, exist_ok=True)
    minute_dir_15m.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ts_code": "sz.300502",
                "period_type": "1min",
                "datetime": now,
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
                "pre_close": 9.9,
                "change": 0.2,
                "pct_chg": 2.02,
            }
        ]
    ).to_parquet(minute_dir_1m / "data.parquet", index=False)
    pd.DataFrame(
        [
            {
                "ts_code": "sz.300502",
                "period_type": "15min",
                "datetime": now - timedelta(minutes=15),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
                "pre_close": 9.9,
                "change": 0.2,
                "pct_chg": 2.02,
            }
        ]
    ).to_parquet(minute_dir_15m / "data.parquet", index=False)

    latest = StockMinuteData.get_latest_data("300502", period_type="15min", limit=1)
    ranged = StockMinuteData.get_data_by_time_range(
        "300502",
        now - timedelta(minutes=30),
        now + timedelta(minutes=30),
        period_type="15min",
    )
    price = StockMinuteData.get_latest_price("300502")
    quality = StockMinuteData.check_data_quality("300502", period_type="15min", hours=24 * 365)

    assert len(latest) == 1
    assert latest[0].ts_code == "sz.300502"
    assert len(ranged) == 1
    assert ranged[0].ts_code == "sz.300502"
    assert price == 10.1
    assert quality["status"] in {"ok", "incomplete"}


def test_stock_minute_data_bulk_insert_keeps_period_partitions(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Use a fixed morning time so now+60min never crosses midnight
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

    ok = StockMinuteData.bulk_insert(
        [
            {
                "ts_code": "sz.300502",
                "period_type": "15min",
                "datetime": now,
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
            },
            {
                "ts_code": "sz.300502",
                "period_type": "60min",
                "datetime": now + timedelta(minutes=60),
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "volume": 1200,
                "amount": 12240.0,
            },
        ]
    )

    reader_15 = Path(tmp_path) / "stock_minute" / "15min" / f"year={now.year:04d}" / f"month={now.month:02d}" / f"day={now.day:02d}" / "data.parquet"
    reader_60 = Path(tmp_path) / "stock_minute" / "60min" / f"year={now.year:04d}" / f"month={now.month:02d}" / f"day={now.day:02d}" / "data.parquet"

    assert ok is True
    assert reader_15.is_file()
    assert reader_60.is_file()
