from unittest.mock import patch

import pytest

from app.services.parquet_state_store import BacktestRepository, ParquetStateStore

pytestmark = pytest.mark.module_backtest


def test_backtest_run_endpoint_returns_parquet_backed_snapshot(app, tmp_path):
    repo = BacktestRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    record = repo.create_run(
        {"selection_method": "factor_based"},
        "2024-01-01",
        "2024-01-31",
        1000000.0,
        "monthly",
    )

    client = app.test_client()
    with patch("app.api.ml_factor_api._backtest_repo", repo):
        response = client.get(f"/api/ml-factor/backtest/runs/{record['id']}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["run"]["id"] == record["id"]
    assert data["run"]["strategy_config"] == {"selection_method": "factor_based"}
