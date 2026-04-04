from pathlib import Path


def test_portfolio_template_does_not_seed_fake_portfolios():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "portfolio_001" not in html
    assert "价值投资组合" not in html
    assert "// 模拟数据" not in html


def test_portfolio_template_hides_fake_create_and_save_paths():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert 'data-bs-target="#createPortfolioModal"' in html
    assert "function createPortfolio()" in html
    assert "function saveOptimizedPortfolio()" in html
    assert "保存为投资组合" in html
    assert "/api/ml-factor/portfolio/save-optimized" in html
    assert "/api/realtime-analysis/risk/portfolio" in html


def test_portfolio_template_uses_real_list_and_detail_endpoints():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "/api/ml-factor/portfolio/list" in html
    assert "/api/ml-factor/portfolio/" in html
    assert "/api/realtime-analysis/risk/portfolio/" in html
    assert "portfolios.find(" not in html
    assert "portfolio.portfolio_id" in html


def test_portfolio_template_supports_real_position_create_and_update_actions():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "新增持仓" in html
    assert "编辑持仓" in html
    assert "function openPositionModal(" in html
    assert "function submitPortfolioPosition(" in html
    assert "method = editingPositionId ? 'put' : 'post'" in html
    assert "/api/realtime-analysis/risk/portfolio/${portfolioId}/positions/${editingPositionId}" in html
