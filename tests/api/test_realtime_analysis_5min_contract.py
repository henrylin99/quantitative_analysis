from unittest.mock import patch

from flask import Flask

from app.api.realtime_analysis import realtime_analysis_bp
from app.api.realtime_indicators import realtime_indicators_bp
from app.api.realtime_monitor import realtime_monitor_bp
from app.api.realtime_signals import realtime_signals_bp


def _build_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(realtime_analysis_bp)
    app.register_blueprint(realtime_indicators_bp, url_prefix="/api/realtime-analysis/indicators")
    app.register_blueprint(realtime_monitor_bp, url_prefix="/api/realtime-analysis/monitor")
    app.register_blueprint(realtime_signals_bp, url_prefix="/api/realtime-analysis/signals")
    return app


def test_indicator_default_period_is_5min():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_indicators.indicator_engine") as engine:
        engine.calculate_indicators.return_value = {"success": True, "data": {}, "data_points": 0, "stored_records": 0}
        response = client.post("/api/realtime-analysis/indicators/calculate", json={"ts_code": "000001.SZ"})

    assert response.status_code == 200
    assert engine.calculate_indicators.call_args.kwargs["period_type"] == "5min"


def test_signal_default_period_is_5min():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_signals.signal_engine") as engine:
        engine.generate_signals.return_value = {"success": True, "data": {}}
        response = client.post("/api/realtime-analysis/signals/generate", json={"ts_code": "000001.SZ"})

    assert response.status_code == 200
    assert engine.generate_signals.call_args.kwargs["period_type"] == "5min"


def test_indicator_supported_endpoint_cold_starts_lazy_engine():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_indicators.indicator_engine", None), patch(
        "app.api.realtime_indicators.RealtimeIndicatorEngine"
    ) as engine_cls:
        engine = engine_cls.return_value
        engine.get_supported_indicators.return_value = [{"code": "MA"}]

        response = client.get("/api/realtime-analysis/indicators/supported")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert engine_cls.called
    assert engine.get_supported_indicators.called


def test_indicator_batch_calculate_cold_starts_lazy_engine():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_indicators.indicator_engine", None), patch(
        "app.api.realtime_indicators.RealtimeIndicatorEngine"
    ) as engine_cls:
        engine = engine_cls.return_value
        engine.calculate_indicators.return_value = {"success": True, "data": {}}

        response = client.post(
            "/api/realtime-analysis/indicators/batch-calculate",
            json={"stock_codes": ["000001.SZ"], "period_type": "5min"},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert engine_cls.called
    assert engine.calculate_indicators.called


def test_signal_backtest_cold_starts_lazy_engine():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_signals.signal_engine", None), patch(
        "app.api.realtime_signals.RealtimeTradingSignalEngine"
    ) as engine_cls:
        engine = engine_cls.return_value
        engine.backtest_strategy.return_value = {"success": True, "data": {}}

        response = client.post(
            "/api/realtime-analysis/signals/backtest",
            json={
                "strategy_name": "trend_following",
                "ts_code": "000001.SZ",
                "start_date": "2026-06-04T09:31:00",
                "end_date": "2026-06-04T11:30:00",
            },
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert engine_cls.called
    assert engine.backtest_strategy.called


def test_monitor_default_period_is_5min():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_monitor.monitor_service") as service:
        service.get_realtime_quotes.return_value = {"success": True, "data": {"quotes": []}}
        response = client.get("/api/realtime-analysis/monitor/quotes")

    assert response.status_code == 200
    assert service.get_realtime_quotes.call_args.kwargs["period_type"] == "5min"


def test_monitor_page_defaults_quote_loading_to_5min():
    from pathlib import Path

    html = Path("app/templates/realtime_analysis/monitor.html").read_text(encoding="utf-8")

    assert "loadQuotes('5min');" in html
    assert "function loadQuotes(periodType = '5min')" in html
