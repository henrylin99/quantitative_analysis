from pathlib import Path

import pandas as pd

from app.services.realtime_risk_manager import RealtimeRiskManager


def _write_minute_assets(tmp_path: Path):
    minute_dir = tmp_path / "stock_minute" / "60min" / "year=2026" / "month=06" / "day=04"
    minute_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "60min",
                "datetime": "2026-06-04T10:00:00",
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
            },
            {
                "ts_code": "000001.SZ",
                "period_type": "60min",
                "datetime": "2026-06-04T11:00:00",
                "open": 10.1,
                "high": 10.4,
                "low": 10.0,
                "close": 10.3,
                "volume": 1500,
                "amount": 15450.0,
            },
        ]
    ).to_parquet(minute_dir / "data.parquet", index=False)

    current_dir = tmp_path / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    current_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": "2026-06-04T11:30:00",
                "open": 10.3,
                "high": 10.5,
                "low": 10.2,
                "close": 10.4,
                "volume": 1800,
                "amount": 18720.0,
            }
        ]
    ).to_parquet(current_dir / "data.parquet", index=False)


def test_risk_manager_reads_current_and_history_prices_from_parquet(tmp_path, monkeypatch):
    _write_minute_assets(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    manager = RealtimeRiskManager()

    price_data = manager._get_price_data(["000001.SZ"], pd.Timestamp("2026-06-04"), pd.Timestamp("2026-06-05"))
    current_price = manager._get_current_price("000001.SZ")

    assert not price_data.empty
    assert "000001.SZ" in price_data.columns
    assert current_price == 10.4
