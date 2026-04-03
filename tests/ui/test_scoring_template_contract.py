from pathlib import Path


def test_scoring_template_hides_unfinished_export_and_portfolio_actions():
    html = Path("app/templates/ml_factor/scoring.html").read_text(encoding="utf-8")

    assert "导出结果" not in html
    assert "创建投资组合" not in html
    assert "function exportResults()" not in html
    assert "function createPortfolio()" not in html
    assert "导出功能待实现" not in html
    assert "创建投资组合功能待实现" not in html
