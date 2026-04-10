import pandas as pd
import pytest

from app.services.factor_expression_engine import FactorExpressionEngine

pytestmark = pytest.mark.module_feature_engineering


def test_expression_engine_supports_pct_change_and_rolling_mean():
    df = pd.DataFrame(
        {
            "close": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            "vol": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
        }
    )

    engine = FactorExpressionEngine()
    out = engine.evaluate("close.pct_change(5) - close.rolling(3).mean()", df)

    assert "factor_value" in out.columns
    assert len(out) == len(df)


def test_expression_engine_rejects_unsafe_expression():
    df = pd.DataFrame({"close": [1, 2, 3]})
    engine = FactorExpressionEngine()

    with pytest.raises(ValueError):
        engine.evaluate("__import__('os').system('echo hacked')", df)
