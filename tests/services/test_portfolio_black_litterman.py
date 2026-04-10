import sys
import types

import pandas as pd

if "cvxpy" not in sys.modules:
    sys.modules["cvxpy"] = types.SimpleNamespace()

import pytest

from app.services.portfolio_optimizer import PortfolioOptimizer

pytestmark = pytest.mark.module_portfolio


def test_black_litterman_returns_successful_weights():
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
        constraints={"tau": 0.05},
    )

    assert result["success"] is True
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
