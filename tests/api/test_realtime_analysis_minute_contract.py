from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from flask import Flask

from app.api.realtime_analysis import realtime_analysis_bp


def _build_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(realtime_analysis_bp)
    return app


def _minute_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": datetime(2026, 6, 4, 9, 31),
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
                "ts_code": "000002.SZ",
                "period_type": "1min",
                "datetime": datetime(2026, 6, 4, 9, 31),
                "open": 20.0,
                "high": 20.2,
                "low": 19.9,
                "close": 20.1,
                "volume": 2000,
                "amount": 40200.0,
                "pre_close": 19.9,
                "change": 0.2,
                "pct_chg": 1.01,
            },
        ]
    )


def test_minute_stock_list_endpoint_uses_parquet_stock_basic():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_stock_list_from_db.return_value = ["000001.SZ", "000002.SZ"]
        response = client.get("/api/realtime-analysis/data/stock-list")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["count"] == 2
    assert data["data"] == ["000001.SZ", "000002.SZ"]


def test_minute_periods_endpoint_uses_manager_periods():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_minute_periods.return_value = ["1min", "5min", "15min"]
        response = client.get("/api/realtime-analysis/data/periods")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"] == ["1min", "5min", "15min"]


def test_minute_stocks_endpoint_uses_manager_stock_list():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_available_minute_stocks.return_value = ["000001.SZ", "000002.SZ"]
        response = client.get("/api/realtime-analysis/data/stocks")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["count"] == 2
    assert data["data"] == ["000001.SZ", "000002.SZ"]


def test_minute_sync_status_endpoint_returns_parquet_summary():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_minute_summary.return_value = {
            "has_data": True,
            "data_count": 2,
            "latest_time": "2026-06-04T09:31:00",
            "earliest_time": "2026-06-04T09:30:00",
            "missing_count": 0,
            "completeness": 100.0,
            "status": "ok",
            "message": "数据完整性: 100.0%",
        }
        response = client.get("/api/realtime-analysis/data/sync-status?ts_code=000001.SZ&period_type=1min")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["has_data"] is True
    assert data["data_count"] == 2
    assert data["latest_time"] == "2026-06-04T09:31:00"


def test_minute_latest_and_range_endpoints_return_json_rows():
    app = _build_app()
    client = app.test_client()
    frame = _minute_frame()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_minute_latest_data.return_value = frame.head(1)
        manager.get_minute_range_data.return_value = frame
        latest_response = client.get("/api/realtime-analysis/data/latest?ts_code=000001.SZ&period_type=1min&limit=1")
        range_response = client.get(
            "/api/realtime-analysis/data/range?ts_code=000001.SZ&start_time=2026-06-04T09:30:00Z&end_time=2026-06-04T09:32:00Z&period_type=1min"
        )

    assert latest_response.status_code == 200
    assert latest_response.get_json()["count"] == 1
    assert latest_response.get_json()["data"][0]["ts_code"] == "000001.SZ"

    assert range_response.status_code == 200
    assert range_response.get_json()["count"] == 2
    assert range_response.get_json()["data"][1]["ts_code"] == "000002.SZ"


def test_minute_stats_and_quality_endpoints_return_summary_contract():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_minute_stats.return_value = {
            "period_stats": {"1min": 2, "5min": 0, "15min": 0, "30min": 0, "60min": 0},
            "total_stocks": 2,
            "latest_time": "2026-06-04T09:31:00",
            "earliest_time": "2026-06-04T09:30:00",
            "total_records": 2,
        }
        manager.check_data_quality.return_value = {
            "status": "ok",
            "message": "数据完整性: 100.0%",
            "data_count": 2,
            "missing_count": 0,
            "completeness": 100.0,
            "latest_time": "2026-06-04T09:31:00",
            "earliest_time": "2026-06-04T09:30:00",
        }
        stats_response = client.get("/api/realtime-analysis/data/stats")
        quality_response = client.get("/api/realtime-analysis/data/quality?ts_code=000001.SZ&period_type=1min&hours=24")

    assert stats_response.status_code == 200
    assert stats_response.get_json()["data"]["total_records"] == 2
    assert quality_response.status_code == 200
    assert quality_response.get_json()["data"]["status"] == "ok"


def test_minute_price_and_market_overview_endpoints_return_parquet_backed_payloads():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.get_realtime_price.return_value = {
            "success": True,
            "message": "获取成功",
            "data": {
                "ts_code": "000001.SZ",
                "current_price": 10.1,
                "change": 0.2,
                "pct_chg": 2.02,
                "volume": 1000,
                "amount": 10100.0,
                "update_time": "2026-06-04T09:31:00",
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
            },
        }
        manager.get_market_overview.return_value = {
            "success": True,
            "message": "获取成功",
            "data": {
                "update_time": "2026-06-04T09:31:00",
                "total_stocks": 2,
                "rising_stocks": 1,
                "falling_stocks": 1,
                "flat_stocks": 0,
                "rising_ratio": 50.0,
                "total_volume": 3000,
                "total_amount": 50300.0,
                "avg_pct_chg": 1.51,
            },
        }
        price_response = client.get("/api/realtime-analysis/data/price?ts_code=000001.SZ")
        overview_response = client.get("/api/realtime-analysis/data/market-overview")

    assert price_response.status_code == 200
    assert price_response.get_json()["data"]["current_price"] == 10.1
    assert overview_response.status_code == 200
    assert overview_response.get_json()["data"]["total_stocks"] == 2
