from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_delete_portfolio_endpoint_soft_deletes_positions(app, tmp_path):
    client = app.test_client()
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000001.SZ",
            "position_size": 100,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 1000.0,
            "unrealized_pnl": 0.0,
            "weight": 50.0,
            "is_active": True,
        }
    )
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000002.SZ",
            "position_size": 100,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 1000.0,
            "unrealized_pnl": 0.0,
            "weight": 50.0,
            "is_active": True,
        }
    )

    with patch("app.api.ml_factor_api._portfolio_repo", repo):
        response = client.delete("/api/ml-factor/portfolio/growth_a")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["portfolio_id"] == "growth_a"
    assert data["deactivated_count"] == 2
    assert repo.list_positions("growth_a") == []


def test_delete_portfolio_endpoint_returns_404_for_missing_portfolio(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api._portfolio_repo") as repo:
        repo.deactivate_portfolio.return_value = 0
        response = client.delete("/api/ml-factor/portfolio/missing")

    assert response.status_code == 404
    data = response.get_json()
    assert "未找到投资组合" in data["error"]
