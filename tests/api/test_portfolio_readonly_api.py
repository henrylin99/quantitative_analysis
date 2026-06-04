from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_portfolio_list_endpoint_returns_real_position_summaries(app, tmp_path):
    client = app.test_client()
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000001.SZ",
            "position_size": 100,
            "avg_cost": 10.0,
            "current_price": 11.0,
            "market_value": 1100.0,
            "unrealized_pnl": 100.0,
            "weight": 60.0,
            "is_active": True,
        }
    )
    repo.upsert_position(
        {
            "portfolio_id": "value_b",
            "ts_code": "000002.SZ",
            "position_size": 50,
            "avg_cost": 20.0,
            "current_price": 19.0,
            "market_value": 950.0,
            "unrealized_pnl": -50.0,
            "weight": 40.0,
            "is_active": True,
        }
    )

    with patch("app.api.ml_factor_api._portfolio_repo", repo):
        response = client.get("/api/ml-factor/portfolio/list")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["total_count"] == 2
    assert data["portfolios"][0]["portfolio_id"] == "growth_a"


def test_portfolio_detail_endpoint_returns_404_when_missing(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api._portfolio_repo") as repo:
        repo.list_positions.return_value = []
        repo.calculate_metrics.return_value = {}
        response = client.get("/api/ml-factor/portfolio/missing")

    assert response.status_code == 404
    data = response.get_json()
    assert "未找到投资组合" in data["error"]
