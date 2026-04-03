from pathlib import Path


def test_portfolio_template_does_not_seed_fake_portfolios():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "portfolio_001" not in html
    assert "价值投资组合" not in html
    assert "// 模拟数据" not in html
