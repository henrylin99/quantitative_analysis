import pytest

from app.services.factor_engine import FactorEngine

pytestmark = pytest.mark.module_factor_engine


def test_get_custom_factor_capabilities_exposes_expression_whitelist():
    engine = FactorEngine()

    capabilities = engine.get_custom_factor_capabilities()

    assert "close" in capabilities["allowed_columns"]
    assert "pct_change" in capabilities["allowed_series_methods"]
    assert "mean" in capabilities["allowed_window_methods"]
    assert "abs" in capabilities["allowed_functions"]
    assert capabilities["examples"]


def test_validate_custom_factor_formula_returns_readable_error():
    engine = FactorEngine()

    result = engine.validate_custom_factor_formula("revenue / close")

    assert result["valid"] is False
    assert "column not allowed" in result["error"]
