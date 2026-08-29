"""回测结果持久化与异步任务的回归测试。"""
import pytest

from app.services.parquet_state_store import BacktestRepository, ParquetStateStore

pytestmark = pytest.mark.module_backtest


def _make_repo(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    return BacktestRepository(store)


def test_result_roundtrip_and_overwrite(tmp_path):
    repo = _make_repo(tmp_path)
    run = repo.create_run(
        strategy_config={"top_n": 5},
        start_date="2026-01-01",
        end_date="2026-01-31",
        initial_capital=1_000_000.0,
        rebalance_frequency="daily",
    )
    run_id = run["id"]

    assert repo.get_result(run_id) is None

    repo.save_result(run_id, {
        "success": True,
        "portfolio_values": [{"date": "2026-01-02", "total_value": 1_000_100.0}],
    })
    got = repo.get_result(run_id)
    assert got["success"] is True
    assert got["portfolio_values"][0]["total_value"] == 1_000_100.0

    # 同一 run_id 覆盖写入，不残留多行
    repo.save_result(run_id, {"success": True, "final_value": 1_100_000.0})
    assert repo.get_result(run_id)["final_value"] == 1_100_000.0
    assert repo.get_result(run_id + 999) is None


def test_async_task_runs_inline_and_persists(monkeypatch, tmp_path):
    """异步任务：执行引擎 → 状态 succeeded → 完整结果落盘。

    summary 采用合并更新：引擎写入的 final_value 等指标不能被状态字段冲掉。
    """
    from app.tasks import backtest_tasks

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(backtest_tasks, "_build_repo", lambda: repo)
    run = repo.create_run(
        strategy_config={}, start_date="2026-01-01", end_date="2026-01-31",
        initial_capital=1_000_000.0, rebalance_frequency="daily",
    )
    run_id = run["id"]

    expected_run_id = run["id"]

    class FakeEngine:
        def run_backtest(self, cfg, start, end, capital, freq, run_id=None):
            assert run_id == expected_run_id, "任务必须把预创建的 run_id 传给引擎"
            # 真实引擎会把指标写入 summary（update_summary 整行覆盖语义）
            repo.update_summary(expected_run_id, {"final_value": 1_234_567.0})
            return {"success": True, "run_id": run_id, "final_value": 1_234_567.0}

    monkeypatch.setattr(backtest_tasks, "_build_engine", lambda: FakeEngine())

    out = backtest_tasks.run_backtest_task(
        run_id, {}, "2026-01-01", "2026-01-31", 1_000_000.0, "daily"
    )

    assert out["status"] == "succeeded"
    assert repo.get_result(run_id)["final_value"] == 1_234_567.0
    summary = repo.get_run(run_id)["summary"]
    assert summary["status"] == "succeeded"
    assert summary["final_value"] == 1_234_567.0, "合并更新失败：引擎指标被状态字段覆盖"


def test_async_task_marks_failed_on_engine_error(monkeypatch, tmp_path):
    """引擎抛异常时任务必须把 run 标记为 failed，不能永远停在 running。"""
    from app.tasks import backtest_tasks

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(backtest_tasks, "_build_repo", lambda: repo)
    run = repo.create_run(
        strategy_config={}, start_date="2026-01-01", end_date="2026-01-31",
        initial_capital=1_000_000.0, rebalance_frequency="daily",
    )
    run_id = run["id"]

    class BoomEngine:
        def run_backtest(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(backtest_tasks, "_build_engine", lambda: BoomEngine())

    out = backtest_tasks.run_backtest_task(
        run_id, {}, "2026-01-01", "2026-01-31", 1_000_000.0, "daily"
    )

    assert out["status"] == "failed"
    summary = repo.get_run(run_id)["summary"]
    assert summary["status"] == "failed"
    assert "boom" in summary["error"]
    assert repo.get_result(run_id) is None
