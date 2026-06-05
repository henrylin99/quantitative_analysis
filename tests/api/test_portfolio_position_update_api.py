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
    class Position:
        def __init__(self):
            self.id = 7
            self.portfolio_id = "growth_a"
            self.ts_code = "000001.SZ"
            self.position_size = 1000.0
            self.avg_cost = 10.0
            self.current_price = 10.0
            self.sector = None
            self.stop_loss_price = None
            self.take_profit_price = None
            self.market_value = None
            self.unrealized_pnl = None

        def to_dict(self):
            return {
                "id": self.id,
                "portfolio_id": self.portfolio_id,
                "ts_code": self.ts_code,
                "position_size": self.position_size,
                "avg_cost": self.avg_cost,
                "current_price": self.current_price,
                "sector": self.sector,
                "stop_loss_price": self.stop_loss_price,
                "take_profit_price": self.take_profit_price,
                "market_value": self.market_value,
                "unrealized_pnl": self.unrealized_pnl,
            }

    def update_position_by_id(*_args, **kwargs):
        position = Position()
        for key, value in kwargs.items():
            if value is not None:
                setattr(position, key, value)
        position.market_value = position.position_size * position.current_price
        position.unrealized_pnl = (position.current_price - position.avg_cost) * position.position_size
        return position

    with patch("app.api.realtime_risk.PortfolioPosition") as portfolio_model:
        portfolio_model.update_position_by_id.side_effect = update_position_by_id

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
    portfolio_model.update_position_by_id.assert_called_once()


def test_update_portfolio_position_endpoint_returns_not_found_when_missing(app):
    client = app.test_client()

    with patch("app.api.realtime_risk.PortfolioPosition") as portfolio_model:
        portfolio_model.update_position_by_id.return_value = None

        response = client.put(
            "/api/realtime-analysis/risk/portfolio/growth_a/positions/7",
            json={"position_size": 1200},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is False
    assert "不存在" in data["message"]
