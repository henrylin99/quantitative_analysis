from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
from flask import Flask

from app.api.realtime_indicators import realtime_indicators_bp


def _build_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(realtime_indicators_bp, url_prefix="/api/realtime-analysis/indicators")
    return app


def _minute_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "5min",
                "datetime": datetime(2026, 6, 4, 9, 35),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
            },
            {
                "ts_code": "000001.SZ",
                "period_type": "5min",
                "datetime": datetime(2026, 6, 4, 9, 40),
                "open": 10.1,
                "high": 10.4,
                "low": 10.0,
                "close": 10.3,
                "volume": 1200,
                "amount": 12360.0,
            },
            {
                "ts_code": "000001.SZ",
                "period_type": "5min",
                "datetime": datetime(2026, 6, 4, 9, 45),
                "open": 10.3,
                "high": 10.5,
                "low": 10.2,
                "close": 10.4,
                "volume": 1500,
                "amount": 15600.0,
            },
        ]
    )


def test_calculate_endpoint_returns_latest_value_summary():
    app = _build_app()
    client = app.test_client()

    payload = {
        "success": True,
        "data": {
            "MA": {"MA5": [None, None, 10.2]},
            "MACD": {"MACD": [None, None, [0.2, 0.1, 0.1]]},
        },
        "total_indicators": 2,
        "data_points": 3,
        "stored_records": 3,
        "latest_values": {
            "MA": {"MA5": 10.2},
            "MACD": {"MACD": [0.2, 0.1, 0.1]},
        },
    }

    with patch("app.api.realtime_indicators.indicator_engine") as engine:
        engine.calculate_indicators.return_value = payload
        response = client.post("/api/realtime-analysis/indicators/calculate", json={"ts_code": "000001.SZ"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "latest_values" in data
    assert data["latest_values"]["MA"]["MA5"] == 10.2


def test_calculate_endpoint_can_boot_indicator_engine_without_preset_global():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_indicators.indicator_engine", None), patch(
        "app.api.realtime_indicators.RealtimeIndicatorEngine"
    ) as engine_cls:
        engine = engine_cls.return_value
        engine.calculate_indicators.return_value = {
            "success": True,
            "data": {},
            "latest_values": {},
            "indicator_summary": {},
            "timeline": [],
            "total_indicators": 0,
            "data_points": 0,
            "stored_records": 0,
        }

        response = client.post(
            "/api/realtime-analysis/indicators/calculate",
            json={"ts_code": "300502", "period_type": "15min", "indicators": ["MA"]},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert engine_cls.called
    assert engine.calculate_indicators.called


def test_multi_period_endpoint_exposes_summary_fields():
    app = _build_app()
    client = app.test_client()

    payload = {
        "success": True,
        "data": {
            "5min": {
                "success": True,
                "data": {"MA": {"MA5": [None, 10.1]}},
                "latest_values": {"MA": {"MA5": 10.1}},
                "total_indicators": 1,
                "data_points": 2,
                "stored_records": 2,
            },
            "15min": {
                "success": True,
                "data": {"MA": {"MA5": [None, 10.2]}},
                "latest_values": {"MA": {"MA5": 10.2}},
                "total_indicators": 1,
                "data_points": 2,
                "stored_records": 2,
            },
        },
        "ts_code": "000001.SZ",
        "indicators": ["MA"],
        "periods": ["5min", "15min"],
        "summary": {
            "period_count": 2,
            "available_periods": ["5min", "15min"],
        },
    }

    with patch("app.api.realtime_indicators.indicator_engine") as engine:
        engine.calculate_multi_period_indicators.return_value = payload
        response = client.post(
            "/api/realtime-analysis/indicators/multi-period",
            json={"ts_code": "000001.SZ", "periods": ["5min", "15min"], "indicators": ["MA"]},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "summary" in data
    assert data["summary"]["period_count"] == 2


def test_compare_endpoint_can_return_empty_state_message():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_indicators.RealtimeIndicator") as model:
        model.get_latest_indicators.return_value = []
        response = client.post(
            "/api/realtime-analysis/indicators/compare",
            json={"stock_codes": ["000001.SZ"], "period_type": "5min", "indicator_name": "MA"},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["000001.SZ"] == []
    assert "empty_state" in data


def test_indicator_stats_endpoint_returns_useful_summary():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_indicators.RealtimeIndicator") as model:
        model.get_indicator_stats.return_value = {
            "total_records": 3,
            "total_stocks": 1,
            "indicator_stats": {"MA": 2, "MACD": 1},
            "period_stats": {"5min": 3},
            "earliest_time": "2026-06-04T09:35:00",
            "latest_time": "2026-06-04T09:45:00",
        }
        response = client.get("/api/realtime-analysis/indicators/stats")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total_records"] == 3
    assert data["period_stats"]["5min"] == 3


def test_indicator_engine_persists_ma_and_ema_rows():
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "5min",
                "datetime": datetime(2026, 6, 4, 9, 35) + timedelta(minutes=i * 5),
                "open": 10.0 + i * 0.1,
                "high": 10.2 + i * 0.1,
                "low": 9.9 + i * 0.1,
                "close": 10.0 + i * 0.1,
                "volume": 1000 + i * 10,
                "amount": 10100.0 + i * 100,
            }
            for i in range(30)
        ]
    )

    class _ColumnComparator:
        def __ge__(self, other):
            return ("ge", other)

    fake_query = SimpleNamespace(
        filter=MagicMock(return_value=SimpleNamespace(delete=MagicMock(return_value=0)))
    )
    fake_model = SimpleNamespace(
        datetime=_ColumnComparator(),
        ts_code=_ColumnComparator(),
        period_type=_ColumnComparator(),
        query=fake_query,
        batch_insert=MagicMock(return_value=(True, "ok")),
    )

    with patch("app.services.realtime_indicator_engine.ParquetDataReader") as reader_cls:
        reader = reader_cls.return_value
        reader.get_minute_reader.return_value.get_data.return_value = frame
        with patch("app.services.realtime_indicator_engine.RealtimeIndicator", new=fake_model):
            from app.services.realtime_indicator_engine import RealtimeIndicatorEngine

            engine = RealtimeIndicatorEngine()
            engine.default_params["MA"]["periods"] = [2]
            engine.default_params["EMA"]["periods"] = [2]
            engine.calculate_indicators("000001.SZ", "5min", indicators=["MA", "EMA"], lookback_days=7)

    inserted = fake_model.batch_insert.call_args.args[0]
    names = {row["indicator_name"] for row in inserted}
    assert "MA" in names
    assert "EMA" in names
