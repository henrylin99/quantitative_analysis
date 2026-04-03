from pathlib import Path


def test_backtest_template_consumes_backend_schema_fields():
    html = Path("app/templates/ml_factor/backtest.html").read_text(encoding="utf-8")

    assert "const returnsData = data.equity_curve || [];" in html
    assert "const drawdownData = data.drawdown_series || [];" in html
    assert "const rollingReturns = data.monthly_returns || [];" in html
    assert "const positions = data.positions || [];" in html
    assert "const riskMetrics = data.risk_metrics || {};" in html
    assert "generatePositionsFromBacktest" not in html
    assert "generateRollingReturnsFromDaily" not in html
    assert "calculateDrawdownFromValues" not in html
