from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_portfolio


def test_delete_portfolio_endpoint_soft_deletes_positions(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model, patch("app.api.ml_factor_api.db") as db:
        rows = [type("Position", (), {"is_active": True})(), type("Position", (), {"is_active": True})()]
        portfolio_model.query.filter_by.return_value.all.return_value = rows

        response = client.delete("/api/ml-factor/portfolio/growth_a")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["portfolio_id"] == "growth_a"
    assert data["deactivated_count"] == 2
    assert all(row.is_active is False for row in rows)
    db.session.commit.assert_called_once()


def test_delete_portfolio_endpoint_returns_404_for_missing_portfolio(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model:
        portfolio_model.query.filter_by.return_value.all.return_value = []

        response = client.delete("/api/ml-factor/portfolio/missing")

    assert response.status_code == 404
    data = response.get_json()
    assert "未找到投资组合" in data["error"]
