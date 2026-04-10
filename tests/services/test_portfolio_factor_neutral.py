import sys
import types

import pandas as pd

if "cvxpy" not in sys.modules:
    sys.modules["cvxpy"] = types.SimpleNamespace()

import pytest

from app.services.portfolio_optimizer import PortfolioOptimizer

pytestmark = pytest.mark.module_portfolio


def test_factor_neutral_weights_control_exposure():
    optimizer = PortfolioOptimizer()
    expected_returns = pd.Series(
        {"A": 0.10, "B": 0.08, "C": 0.06}
    )
    risk_model = pd.DataFrame(
        [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 0.1]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    exposures = pd.DataFrame(
        {"value": [1.0, 0.2, -1.0]},
        index=["A", "B", "C"],
    )

    result = optimizer.optimize_portfolio(
        expected_returns,
        risk_model=risk_model,
        method="factor_neutral",
        constraints={
            "factor_exposures": exposures,
            "exposure_tolerance": 1e-3,
            "risk_aversion": 1.0,
        },
    )

    assert result.get("success") is True
    weights = result["weights"]
    portfolio_exposure = sum(weights[code] * exposures.loc[code, "value"] for code in weights)
    assert abs(portfolio_exposure) <= 1e-3 + 1e-6


def test_optimize_portfolio_applies_supported_industry_constraints():
    optimizer = PortfolioOptimizer()
    expected_returns = pd.Series({"A": 0.10, "B": 0.08})
    risk_model = pd.DataFrame(
        [[0.1, 0.0], [0.0, 0.1]],
        index=["A", "B"],
        columns=["A", "B"],
    )

    result = optimizer.optimize_portfolio(
        expected_returns,
        risk_model=risk_model,
        method="equal_weight",
        constraints={
            "industry_constraints": {"银行": {"max_weight": 0.3}},
            "industry_map": {"A": "银行", "B": "地产"},
        },
    )

    assert result.get("success") is True
    assert result["weights"]["A"] <= 0.3 + 1e-6


def test_factor_neutral_requires_valid_factor_exposures():
    optimizer = PortfolioOptimizer()
    expected_returns = pd.Series({"A": 0.10, "B": 0.08})
    risk_model = pd.DataFrame(
        [[0.1, 0.0], [0.0, 0.1]],
        index=["A", "B"],
        columns=["A", "B"],
    )

    result = optimizer.optimize_portfolio(
        expected_returns,
        risk_model=risk_model,
        method="factor_neutral",
        constraints={},
    )

    assert "error" in result
    assert "factor_exposures" in result["error"]


def test_optimize_portfolio_supports_black_litterman():
    optimizer = PortfolioOptimizer()
    expected_returns = pd.Series({"A": 0.10, "B": 0.08})
    risk_model = pd.DataFrame(
        [[0.1, 0.0], [0.0, 0.1]],
        index=["A", "B"],
        columns=["A", "B"],
    )

    result = optimizer.optimize_portfolio(
        expected_returns,
        risk_model=risk_model,
        method="black_litterman",
        constraints={},
    )

    assert result.get("success") is True
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
