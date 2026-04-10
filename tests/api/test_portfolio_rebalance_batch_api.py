from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_portfolio


def test_portfolio_rebalance_apply_records_batch_run(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "target_weights": {
            "000001.SZ": 0.6,
            "000002.SZ": 0.4,
        },
        "rebalance_note": "quarterly rebalance",
    }
    existing_a = type(
        "Position",
        (),
        {
            "ts_code": "000001.SZ",
            "position_size": 600.0,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 6000.0,
            "weight": 60.0,
            "is_active": True,
            "sector": "银行",
        },
    )()
    existing_b = type(
        "Position",
        (),
        {
            "ts_code": "000002.SZ",
            "position_size": 400.0,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 4000.0,
            "weight": 40.0,
            "is_active": True,
            "sector": "地产",
        },
    )()
    rebalance_run = type("RebalanceRun", (), {"id": 12})()

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model, patch("app.api.ml_factor_api.StockDailyHistory") as price_model, patch("app.api.ml_factor_api.PortfolioRebalanceRun") as rebalance_model, patch("app.api.ml_factor_api.db") as db:
        portfolio_model.get_portfolio_positions.return_value = [existing_a, existing_b]
        portfolio_model.get_position_by_stock.side_effect = [existing_a, existing_b]
        price_model.query.filter.return_value.order_by.return_value.first.side_effect = [
            type("Price", (), {"close": 11.0})(),
            type("Price", (), {"close": 9.0})(),
        ]
        rebalance_model.create_run.return_value = rebalance_run

        response = client.post("/api/ml-factor/portfolio/rebalance/apply", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["rebalance_run_id"] == 12
    assert data["rebalance_note"] == "quarterly rebalance"
    rebalance_model.create_run.assert_called_once()
    db.session.commit.assert_called_once()
