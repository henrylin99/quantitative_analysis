import sys
import types

import pandas as pd

if "cvxpy" not in sys.modules:
    sys.modules["cvxpy"] = types.SimpleNamespace()

from app.services.portfolio_optimizer import PortfolioOptimizer


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


def test_optimize_portfolio_rejects_unsupported_industry_constraints():
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
            "industry_constraints": {"银行": {"max_weight": 0.3}}
        },
    )

    assert "error" in result
    assert "industry_constraints" in result["error"]


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


def test_optimize_portfolio_rejects_black_litterman_placeholder():
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

    assert "error" in result
    assert "不支持的优化方法" in result["error"]
