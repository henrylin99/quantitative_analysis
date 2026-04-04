from unittest.mock import patch


def test_rebalance_portfolio_endpoint_returns_trade_preview(app):
    client = app.test_client()

    payload = {
        "current_weights": {
            "000001.SZ": 0.6,
            "000002.SZ": 0.4,
        },
        "target_weights": {
            "000001.SZ": 0.5,
            "000002.SZ": 0.3,
            "000003.SZ": 0.2,
        },
        "transaction_cost": 0.002,
    }

    with patch("app.api.ml_factor_api.get_portfolio_optimizer") as get_optimizer:
        get_optimizer.return_value.rebalance_portfolio.return_value = {
            "success": True,
            "trade_instructions": {
                "000001.SZ": -0.1,
                "000002.SZ": -0.1,
                "000003.SZ": 0.2,
            },
            "turnover": 0.2,
            "transaction_cost": 0.0004,
        }

        response = client.post("/api/ml-factor/portfolio/rebalance", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["turnover"] == 0.2
    assert data["trade_instructions"]["000003.SZ"] == 0.2


def test_rebalance_portfolio_endpoint_rejects_missing_weights(app):
    client = app.test_client()

    response = client.post("/api/ml-factor/portfolio/rebalance", json={"current_weights": {"000001.SZ": 1.0}})

    assert response.status_code == 400
    data = response.get_json()
    assert "缺少必需参数" in data["error"]


def test_apply_rebalance_endpoint_updates_existing_positions_and_creates_new_ones(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "target_weights": {
            "000001.SZ": 0.5,
            "000003.SZ": 0.5,
        },
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
            "position_size": 200.0,
            "avg_cost": 20.0,
            "current_price": 20.0,
            "market_value": 4000.0,
            "weight": 40.0,
            "is_active": True,
            "sector": "地产",
        },
    )()

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model, patch("app.api.ml_factor_api.StockDailyHistory") as price_model, patch("app.api.ml_factor_api.db") as db:
        portfolio_model.get_portfolio_positions.return_value = [existing_a, existing_b]
        portfolio_model.get_position_by_stock.side_effect = [existing_a, None]
        price_model.query.filter.return_value.order_by.return_value.first.side_effect = [
            type("Price", (), {"close": 11.0})(),
            type("Price", (), {"close": 25.0})(),
        ]
        portfolio_model.return_value = type("Created", (), {})()

        response = client.post("/api/ml-factor/portfolio/rebalance/apply", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["updated_count"] == 1
    assert data["created_count"] == 1
    assert data["deactivated_count"] == 1
    assert existing_a.position_size == 10000 / 11.0 * 0.5
    assert existing_b.is_active is False
    db.session.add.assert_called_once()
    db.session.commit.assert_called_once()


def test_apply_rebalance_endpoint_rejects_missing_portfolio(app):
    client = app.test_client()

    response = client.post("/api/ml-factor/portfolio/rebalance/apply", json={"portfolio_id": "missing", "target_weights": {"000001.SZ": 1.0}})

    assert response.status_code == 404
    data = response.get_json()
    assert "未找到投资组合" in data["error"]
