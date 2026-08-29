"""僵尸 run 回收合约：worker 被杀留下的 running run 必须能被清理，不再永久阻塞重提。"""
import pytest

from app.services.data_jobs import parquet_state_store as pjss
from app.services.data_jobs.parquet_state_store import ParquetDataJobStateStore

pytestmark = pytest.mark.module_data_jobs


def _create_running_run(store: ParquetDataJobStateStore, job_type: str):
    run = store.create_run(job_type, {"trade_date": "20260601"})
    return store.update_run_status(run, "running", progress_message="开始执行")


def test_reap_stale_runs_marks_old_running_as_failed(monkeypatch, tmp_path):
    store = ParquetDataJobStateStore(base_dir=str(tmp_path / "state"))
    run = _create_running_run(store, "daily_basic")

    real_now = pjss.now_local
    monkeypatch.setattr(pjss, "now_local", lambda: real_now() + __import__("datetime").timedelta(hours=3))

    reaped = store.reap_stale_runs(timeout_seconds=3600)

    assert [r.id for r in reaped] == [run.id]
    refreshed = store.get_run(run.id)
    assert refreshed.status == "failed"
    assert "僵尸" in refreshed.error_message
    # 清理后不再阻塞重复提交
    assert store.find_active_duplicate("daily_basic", {"trade_date": "20260601"}) is None


def test_reap_stale_runs_leaves_fresh_runs_alone(tmp_path):
    store = ParquetDataJobStateStore(base_dir=str(tmp_path / "state"))
    fresh = _create_running_run(store, "stk_factor")

    reaped = store.reap_stale_runs(timeout_seconds=3600)

    assert reaped == []
    assert store.get_run(fresh.id).status == "running"


def test_reap_stale_runs_handles_pending_without_started_at(monkeypatch, tmp_path):
    """pending run 没有 started_at，用 created_at 兜底判超时。"""
    store = ParquetDataJobStateStore(base_dir=str(tmp_path / "state"))
    run = store.create_run("moneyflow", {})

    real_now = pjss.now_local
    monkeypatch.setattr(pjss, "now_local", lambda: real_now() + __import__("datetime").timedelta(hours=3))

    reaped = store.reap_stale_runs(timeout_seconds=3600)

    assert [r.id for r in reaped] == [run.id]
    assert store.get_run(run.id).status == "failed"
