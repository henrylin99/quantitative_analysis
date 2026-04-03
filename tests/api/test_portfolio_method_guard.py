from unittest.mock import patch


def test_portfolio_optimize_rejects_unsupported_method(app):
    client = app.test_client()

    response = client.post(
        "/api/ml-factor/portfolio/optimize",
        json={
            "expected_returns": {"000001.SZ": 0.1, "000002.SZ": 0.08},
            "method": "max_sharpe",
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "不支持的优化方法" in data["error"]


def test_integrated_selection_rejects_unsupported_optimization_method(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_scoring_engine") as get_scoring_engine:
        get_scoring_engine.return_value.calculate_factor_scores.return_value.empty = False
        get_scoring_engine.return_value.calculate_composite_score.return_value.empty = False
        get_scoring_engine.return_value.rank_stocks.return_value = [
            {"ts_code": "000001.SZ", "composite_score": 1.0}
        ]

        response = client.post(
            "/api/ml-factor/portfolio/integrated-selection",
            json={
                "trade_date": "2024-01-31",
                "selection_method": "factor_based",
                "factor_list": ["momentum_5d"],
                "optimization_method": "min_variance",
            },
        )

    assert response.status_code == 400
    data = response.get_json()
    assert "不支持的优化方法" in data["error"]
