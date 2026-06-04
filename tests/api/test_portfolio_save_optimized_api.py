from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_save_optimized_portfolio_creates_real_positions(app, tmp_path):
    client = app.test_client()
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

    payload = {
        "portfolio_id": "growth_a",
        "total_capital": 1000000,
        "weights": {
            "000001.SZ": 0.6,
            "000002.SZ": 0.4,
        },
    }

    with patch("app.api.ml_factor_api._portfolio_repo", repo), patch("app.api.ml_factor_api._data_reader.get_latest_close", side_effect=[10.0, 20.0]):
        response = client.post("/api/ml-factor/portfolio/save-optimized", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["created_count"] == 2
    assert len(repo.list_positions("growth_a")) == 2


def test_save_optimized_portfolio_rejects_existing_active_portfolio(app, tmp_path):
    client = app.test_client()
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000001.SZ",
            "position_size": 10,
            "avg_cost": 10,
            "current_price": 10,
            "market_value": 100,
            "unrealized_pnl": 0,
            "weight": 100,
            "is_active": True,
        }
    )

    payload = {
        "portfolio_id": "growth_a",
        "total_capital": 1000000,
        "weights": {"000001.SZ": 1.0},
    }

    with patch("app.api.ml_factor_api._portfolio_repo", repo):
        response = client.post("/api/ml-factor/portfolio/save-optimized", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert "已存在" in data["error"]
