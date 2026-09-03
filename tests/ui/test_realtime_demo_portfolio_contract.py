from pathlib import Path


def test_risk_management_template_has_no_demo_portfolio_default():
    html = Path("app/templates/realtime_analysis/risk_management.html").read_text(encoding="utf-8")

    assert 'value="demo_portfolio"' not in html
    assert "let currentPortfolioId = 'demo_portfolio';" not in html


def test_report_management_template_has_no_demo_portfolio_default():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert 'value="demo_portfolio"' not in html
