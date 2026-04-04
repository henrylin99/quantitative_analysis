from unittest.mock import patch


def test_save_optimized_portfolio_creates_real_positions(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "total_capital": 1000000,
        "weights": {
            "000001.SZ": 0.6,
            "000002.SZ": 0.4,
        },
    }

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model, patch("app.api.ml_factor_api.StockDailyHistory") as price_model, patch("app.api.ml_factor_api.db") as db:
        portfolio_model.query.filter_by.return_value.first.return_value = None
        price_model.query.filter.return_value.order_by.return_value.first.side_effect = [
            type("Price", (), {"close": 10.0})(),
            type("Price", (), {"close": 20.0})(),
        ]

        response = client.post("/api/ml-factor/portfolio/save-optimized", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["created_count"] == 2
    db.session.add.call_count == 2
    db.session.commit.assert_called_once()


def test_save_optimized_portfolio_rejects_existing_active_portfolio(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "total_capital": 1000000,
        "weights": {"000001.SZ": 1.0},
    }

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model:
        portfolio_model.query.filter_by.return_value.first.return_value = object()

        response = client.post("/api/ml-factor/portfolio/save-optimized", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert "已存在" in data["error"]
