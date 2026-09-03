from app.services.parquet_state_store import BacktestRepository, ParquetStateStore


def test_backtest_repository_allocates_ids_and_round_trips_summary(tmp_path):
    repo = BacktestRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

    run = repo.create_run(
        {"strategy": "mean_reversion"},
        "2024-01-01",
        "2024-01-31",
        1_000_000,
        "monthly",
    )
    assert run["id"] == 1
    assert repo.get_run(1)["strategy_config"] == {"strategy": "mean_reversion"}

    updated = repo.update_summary(1, {"annual_return": 0.12, "sharpe": 1.3})
    assert updated["summary"] == {"annual_return": 0.12, "sharpe": 1.3}
    assert repo.list_runs()[0]["id"] == 1
