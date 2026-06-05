from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from flask import Flask

from app.api.realtime_indicators import realtime_indicators_bp


class _BlockedQuery:
    def filter(self, *args, **kwargs):
        raise AssertionError("indicator flow should not touch ORM-backed storage")


class _BlockedRealtimeIndicator:
    query = _BlockedQuery()

    @staticmethod
    def batch_insert(*args, **kwargs):
        raise AssertionError("indicator flow should not write through ORM-backed storage")


def _write_minute_parquet(root: Path) -> None:
    minute_dir = root / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    minute_dir.mkdir(parents=True, exist_ok=True)

    base_time = datetime(2026, 6, 4, 9, 31)
    rows = []
    for idx in range(60):
        dt = base_time + timedelta(minutes=idx)
        close = 10.0 + idx * 0.05
        rows.append(
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": dt,
                "open": close - 0.05,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": 1000 + idx * 20,
                "amount": (1000 + idx * 20) * close,
            }
        )

    pd.DataFrame(rows).to_parquet(minute_dir / "data.parquet", index=False)


def _build_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(realtime_indicators_bp, url_prefix="/api/realtime-analysis/indicators")
    return app


def test_indicator_calculation_runs_without_orm_backed_mysql_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_minute_parquet(tmp_path)

    with patch("app.services.realtime_indicator_engine.RealtimeIndicator", _BlockedRealtimeIndicator):
        with _build_app().test_client() as client:
            response = client.post(
                "/api/realtime-analysis/indicators/calculate",
                json={
                    "ts_code": "000001.SZ",
                    "period_type": "1min",
                    "indicators": ["RSI"],
                    "lookback_days": 7,
                },
            )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["stored_records"] > 0
