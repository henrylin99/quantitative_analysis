from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_portfolio_list_and_detail_use_parquet_state(app, tmp_path):
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000001.SZ",
            "position_size": 1000,
            "avg_cost": 12.5,
            "current_price": 13.0,
            "market_value": 13000,
            "unrealized_pnl": 500,
            "weight": 60.0,
            "sector": "银行",
            "is_active": True,
        }
    )
    repo.upsert_position(
        {
            "portfolio_id": "value_b",
            "ts_code": "000002.SZ",
            "position_size": 500,
            "avg_cost": 20.0,
            "current_price": 19.0,
            "market_value": 9500,
            "unrealized_pnl": -500,
            "weight": 40.0,
            "sector": "科技",
            "is_active": True,
        }
    )

    client = app.test_client()
    with patch("app.api.ml_factor_api._portfolio_repo", repo):
        response = client.get("/api/ml-factor/portfolio/list")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["total_count"] == 2
        assert data["portfolios"][0]["portfolio_id"] == "growth_a"

        response = client.get("/api/ml-factor/portfolio/growth_a")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["portfolio"]["portfolio_id"] == "growth_a"
    assert data["portfolio"]["positions"][0]["ts_code"] == "000001.SZ"


def test_portfolio_save_and_delete_use_parquet_state(app, tmp_path, monkeypatch):
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    client = app.test_client()

    with (
        patch("app.api.ml_factor_api._portfolio_repo", repo),
        patch("app.api.ml_factor_api._data_reader.get_latest_close", side_effect=[10.0, 20.0]),
    ):
        response = client.post(
            "/api/ml-factor/portfolio/save-optimized",
            json={
                "portfolio_id": "growth_a",
                "total_capital": 1000000,
                "weights": {"000001.SZ": 0.6, "000002.SZ": 0.4},
            },
        )
        assert response.status_code == 200
        assert response.get_json()["created_count"] == 2

        response = client.delete("/api/ml-factor/portfolio/growth_a")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["deactivated_count"] == 2


def test_portfolio_create_and_detail_use_parquet_state(app, tmp_path):
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    client = app.test_client()

    with patch("app.api.ml_factor_api._portfolio_repo", repo):
        response = client.post(
            "/api/ml-factor/portfolio",
            json={
                "portfolio_id": "growth_a",
                "ts_code": "000001.SZ",
                "position_size": 1000,
                "avg_cost": 12.5,
                "sector": "银行",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["portfolio_id"] == "growth_a"
        assert data["data"]["ts_code"] == "000001.SZ"

        response = client.get("/api/ml-factor/portfolio/growth_a")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["portfolio"]["portfolio_id"] == "growth_a"
    assert data["portfolio"]["positions"][0]["ts_code"] == "000001.SZ"
