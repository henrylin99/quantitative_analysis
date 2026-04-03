from pathlib import Path


def test_factor_management_template_hides_unfinished_edit_delete_actions():
    html = Path("app/templates/ml_factor/index.html").read_text(encoding="utf-8")

    assert "onclick=\"editFactor(" not in html
    assert "onclick=\"deleteFactor(" not in html
    assert "function editFactor(" not in html
    assert "function deleteFactor(" not in html


def test_portfolio_template_hides_unfinished_portfolio_actions():
    html = Path("app/templates/ml_factor/portfolio.html").read_text(encoding="utf-8")

    assert "onclick=\"rebalancePortfolio(" not in html
    assert "onclick=\"editPortfolio(" not in html
    assert "onclick=\"deletePortfolio(" not in html
    assert "function rebalancePortfolio(" not in html
    assert "function editPortfolio(" not in html
    assert "function deletePortfolio(" not in html


def test_models_template_hides_unfinished_delete_action():
    html = Path("app/templates/ml_factor/models.html").read_text(encoding="utf-8")

    assert "onclick=\"deleteModel(" not in html
    assert "function deleteModel(" not in html
