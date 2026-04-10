from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_portfolio


def test_portfolio_optimize_accepts_supported_industry_constraints(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_portfolio_optimizer") as get_optimizer:
        get_optimizer.return_value.optimize_portfolio.return_value = {
            "success": True,
            "weights": {"000001.SZ": 0.3, "000002.SZ": 0.7},
            "portfolio_stats": {"max_weight": 0.7},
        }

        response = client.post(
            "/api/ml-factor/portfolio/optimize",
            json={
                "expected_returns": {"000001.SZ": 0.1, "000002.SZ": 0.08},
                "method": "equal_weight",
                "constraints": {
                    "industry_constraints": {"银行": {"max_weight": 0.3}},
                    "industry_map": {"000001.SZ": "银行", "000002.SZ": "地产"},
                },
            },
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["weights"]["000001.SZ"] == 0.3
