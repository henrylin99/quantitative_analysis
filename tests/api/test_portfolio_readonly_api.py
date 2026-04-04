from unittest.mock import patch


def test_portfolio_list_endpoint_returns_real_position_summaries(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model:
        portfolio_model.query.with_entities.return_value.filter_by.return_value.distinct.return_value.all.return_value = [
            ("growth_a",),
            ("value_b",),
        ]
        portfolio_model.calculate_portfolio_metrics.side_effect = [
            {
                "total_positions": 2,
                "total_market_value": 1000000,
                "total_unrealized_pnl": 50000,
                "total_pnl_percentage": 5.0,
                "max_position_weight": 60.0,
            },
            {
                "total_positions": 3,
                "total_market_value": 800000,
                "total_unrealized_pnl": -20000,
                "total_pnl_percentage": -2.5,
                "max_position_weight": 40.0,
            },
        ]
        portfolio_model.query.filter_by.return_value.order_by.return_value.first.side_effect = [
            type("Row", (), {"created_at": None})(),
            type("Row", (), {"created_at": None})(),
        ]

        response = client.get("/api/ml-factor/portfolio/list")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["total_count"] == 2
    assert data["portfolios"][0]["portfolio_id"] == "growth_a"


def test_portfolio_detail_endpoint_returns_404_when_missing(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model:
        portfolio_model.get_portfolio_positions.return_value = []
        portfolio_model.calculate_portfolio_metrics.return_value = {}

        response = client.get("/api/ml-factor/portfolio/missing")

    assert response.status_code == 404
    data = response.get_json()
    assert "未找到投资组合" in data["error"]
