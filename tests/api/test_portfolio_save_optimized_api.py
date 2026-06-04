from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_portfolio


def test_save_optimized_portfolio_creates_real_positions(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "total_capital": 1000000,
        "weights": {
            "000001.SZ": 0.6,
            "000002.SZ": 0.4,
        },
    }

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model, patch("app.api.ml_factor_api._data_reader") as data_reader, patch("app.api.ml_factor_api.db") as db:
        portfolio_model.query.filter_by.return_value.first.return_value = None
        data_reader.get_latest_close.side_effect = [10.0, 20.0]

        response = client.post("/api/ml-factor/portfolio/save-optimized", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["created_count"] == 2
    db.session.add.call_count == 2
    db.session.commit.assert_called_once()


def test_save_optimized_portfolio_rejects_existing_active_portfolio(app):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "total_capital": 1000000,
        "weights": {"000001.SZ": 1.0},
    }

    with patch("app.api.ml_factor_api.PortfolioPosition") as portfolio_model:
        portfolio_model.query.filter_by.return_value.first.return_value = object()

        response = client.post("/api/ml-factor/portfolio/save-optimized", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert "已存在" in data["error"]
