from pathlib import Path

import pytest

pytestmark = pytest.mark.module_portfolio


def test_portfolio_template_exposes_only_supported_optimization_methods():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert 'option value="mean_variance"' in html
    assert 'option value="risk_parity"' in html
    assert 'option value="equal_weight"' in html
    assert 'option value="max_sharpe"' not in html
    assert 'option value="min_variance"' not in html
    assert "showOptimizationWarning" not in html
    assert "回退到等权重优化方法" not in html


def test_scoring_template_hides_hybrid_placeholder_method():
    html = Path("app/templates/ml_factor/scoring.html").read_text(encoding="utf-8")

    assert 'option value="factor_based"' in html
    assert 'option value="ml_based"' in html
    assert 'option value="hybrid"' not in html
    assert "/api/ml-factor/portfolio/integrated-selection" not in html
