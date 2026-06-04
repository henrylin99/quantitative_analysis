from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_portfolio_rebalance_apply_records_batch_run(app, tmp_path):
    client = app.test_client()
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000001.SZ",
            "position_size": 600.0,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 6000.0,
            "weight": 60.0,
            "is_active": True,
            "sector": "银行",
        }
    )
    repo.upsert_position(
        {
            "portfolio_id": "growth_a",
            "ts_code": "000002.SZ",
            "position_size": 400.0,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 4000.0,
            "weight": 40.0,
            "is_active": True,
            "sector": "地产",
        }
    )

    payload = {
        "portfolio_id": "growth_a",
        "target_weights": {
            "000001.SZ": 0.6,
            "000002.SZ": 0.4,
        },
        "rebalance_note": "quarterly rebalance",
    }

    with patch("app.api.ml_factor_api._portfolio_repo", repo), patch("app.api.ml_factor_api._data_reader.get_latest_close", side_effect=[11.0, 9.0]):
        response = client.post("/api/ml-factor/portfolio/rebalance/apply", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["rebalance_run_id"] is None
    assert data["rebalance_note"] == "quarterly rebalance"
