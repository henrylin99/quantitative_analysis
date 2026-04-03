from pathlib import Path


def test_backtest_template_does_not_use_hardcoded_risk_metric_defaults():
    html = Path("app/templates/ml_factor/backtest.html").read_text(encoding="utf-8")

    assert "|| -0.023" not in html
    assert "|| -0.034" not in html
    assert "|| 0.89" not in html
    assert "|| 0.045" not in html
    assert "|| 0.67" not in html
    assert "|| 1.02" not in html
