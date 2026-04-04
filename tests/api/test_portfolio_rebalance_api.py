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
