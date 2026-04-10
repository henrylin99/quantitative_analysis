from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_portfolio


def test_create_portfolio_position_endpoint_creates_first_position(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "ts_code": "000001.SZ",
        "position_size": 1000,
        "avg_cost": 12.5,
        "sector": "银行",
    }

    with patch("app.api.realtime_risk.PortfolioPosition") as portfolio_model, patch("app.api.realtime_risk.db") as db:
        portfolio_model.get_position_by_stock.return_value = None
        portfolio_model.return_value.to_dict.return_value = {
            "portfolio_id": "growth_a",
            "ts_code": "000001.SZ",
        }

        response = client.post("/api/realtime-analysis/risk/portfolio", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["portfolio_id"] == "growth_a"
    db.session.add.assert_called_once()
    db.session.commit.assert_called_once()


def test_create_portfolio_position_endpoint_rejects_duplicate_stock(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "ts_code": "000001.SZ",
        "position_size": 1000,
        "avg_cost": 12.5,
    }

    with patch("app.api.realtime_risk.PortfolioPosition") as portfolio_model:
        portfolio_model.get_position_by_stock.return_value = object()

        response = client.post("/api/realtime-analysis/risk/portfolio", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is False
    assert "已存在" in data["message"]
