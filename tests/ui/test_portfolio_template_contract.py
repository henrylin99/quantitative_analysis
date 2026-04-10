from pathlib import Path

import pytest

pytestmark = pytest.mark.module_portfolio


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


def test_portfolio_template_empty_state_matches_real_crud_availability():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "暂无真实投资组合，请先创建组合或保存优化结果。" in html
    assert "请先完成真实组合 CRUD 后再开放此页面" not in html


def test_portfolio_template_marks_scope_as_minimal_real_crud():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "当前页面提供真实组合管理、优化结果落库和再平衡执行入口。" in html
    assert "智能构建和优化投资组合" not in html


def test_portfolio_template_supports_rebalance_preview_entry():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "再平衡预览" in html
    assert "function previewPortfolioRebalance(" in html
    assert "/api/ml-factor/portfolio/rebalance" in html
    assert "function applyPortfolioRebalance(" in html
    assert "/api/ml-factor/portfolio/rebalance/apply" in html
