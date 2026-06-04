from flask import Flask
from types import SimpleNamespace
from unittest.mock import patch

from app.api.stock_api import api_bp


def test_stock_financials_endpoint_returns_three_statements():
    app = Flask(__name__)
    app.register_blueprint(api_bp, url_prefix="/api")
    client = app.test_client()

    fake_payload = {
        "balance_sheet": {"end_date": "2026-03-31", "total_assets": 100},
        "income_statement": {"end_date": "2026-03-31", "total_revenue": 80},
        "cash_flow": {"end_date": "2026-03-31", "n_cashflow_act": 20},
    }
    fake_service = SimpleNamespace(get_financials=lambda ts_code: fake_payload)

    with patch("app.api.stock_api.StockService", fake_service):
        resp = client.get("/api/stocks/000001.SZ/financials")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == 200
    assert set(data["data"].keys()) == {"balance_sheet", "income_statement", "cash_flow"}
