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


def test_backtest_async_enqueue_returns_run_id_without_task_id(app, tmp_path):
    repo = BacktestRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    client = app.test_client()

    with patch("app.api.ml_factor_api._backtest_repo", repo), patch(
        "app.tasks.backtest_tasks.run_backtest_task"
    ):
        response = client.post(
            "/api/ml-factor/backtest/run",
            json={
                "strategy_config": {"selection_method": "factor_based"},
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "mode": "async",
            },
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["queued"] is True
    assert data["run_id"] > 0
    assert "task_id" not in data  # 去 Celery 后无任务队列 id，字段已移除
    assert data["status_url"] == f"/api/ml-factor/backtest/runs/{data['run_id']}"
    assert data["result_url"] == f"/api/ml-factor/backtest/runs/{data['run_id']}/result"

    run = repo.get_run(data["run_id"])
    assert run["summary"]["status"] == "queued"
