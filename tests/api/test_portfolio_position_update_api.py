from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_portfolio


def test_update_portfolio_position_endpoint_updates_supported_fields(app):
    client = app.test_client()

    payload = {
        "position_size": 1200,
        "avg_cost": 10.5,
        "current_price": 11.2,
        "sector": "银行",
        "stop_loss_price": 9.8,
        "take_profit_price": 12.6,
    }
    position = type(
        "Position",
        (),
        {
            "position_size": 1000.0,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "sector": None,
            "stop_loss_price": None,
            "take_profit_price": None,
            "market_value": None,
            "unrealized_pnl": None,
            "to_dict": lambda self: {
                "id": 7,
                "portfolio_id": "growth_a",
                "ts_code": "000001.SZ",
                "position_size": self.position_size,
                "avg_cost": self.avg_cost,
                "current_price": self.current_price,
                "sector": self.sector,
                "stop_loss_price": self.stop_loss_price,
                "take_profit_price": self.take_profit_price,
                "market_value": self.market_value,
                "unrealized_pnl": self.unrealized_pnl,
            },
        },
    )()

    with patch("app.api.realtime_risk.PortfolioPosition") as portfolio_model, patch("app.api.realtime_risk.db") as db:
        portfolio_model.query.filter_by.return_value.first.return_value = position

        response = client.put("/api/realtime-analysis/risk/portfolio/growth_a/positions/7", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["position_size"] == 1200.0
    assert data["data"]["avg_cost"] == 10.5
    assert data["data"]["current_price"] == 11.2
    assert data["data"]["sector"] == "银行"
    assert data["data"]["market_value"] == 13440.0
    assert data["data"]["unrealized_pnl"] == pytest.approx(840.0)
    db.session.commit.assert_called_once()


def test_update_portfolio_position_endpoint_returns_not_found_when_missing(app):
    client = app.test_client()

    with patch("app.api.realtime_risk.PortfolioPosition") as portfolio_model:
        portfolio_model.query.filter_by.return_value.first.return_value = None

        response = client.put(
            "/api/realtime-analysis/risk/portfolio/growth_a/positions/7",
            json={"position_size": 1200},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is False
    assert "不存在" in data["message"]
