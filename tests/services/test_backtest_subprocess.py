"""回测子进程隔离：派发开关、pid 心跳活性、worker 入口兜底。"""

from __future__ import annotations

import os

import pytest

from app.services.parquet_state_store import BacktestRepository, ParquetStateStore
from app.tasks import backtest_tasks
from app.tasks.backtest_worker import main as worker_main

pytestmark = pytest.mark.module_backtest


@pytest.fixture()
def repo(tmp_path):
    return BacktestRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))


def _new_run(repo):
    run = repo.create_run({"selection_method": "factor_based"},
                          "2024-01-01", "2024-01-31", 1000000.0, "monthly")
    repo.update_summary(run["id"], {"status": "queued"})
    return int(run["id"])


def test_subprocess_disabled_falls_back_inline(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("BACKTEST_SUBPROCESS_ENABLED", "0")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_id = _new_run(repo)
    called = {}

    def _fake_execute(rid):
        called["rid"] = rid
        return {"run_id": rid, "status": "succeeded"}

    monkeypatch.setattr(backtest_tasks, "execute_run", _fake_execute)
    result = backtest_tasks.run_backtest_task(
        run_id, {"selection_method": "factor_based"},
        "2024-01-01", "2024-01-31")
    assert result["status"] == "succeeded"
    assert called["rid"] == run_id
    # 线程内模式执行时必须在册，结束后出册
    assert not backtest_tasks.is_run_active(run_id)


def test_worker_pid_liveness_roundtrip(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_id = _new_run(repo)
    assert not backtest_tasks.is_run_active(run_id)
    backtest_tasks._write_worker_pid(run_id)
    assert backtest_tasks.is_run_active(run_id)  # 本进程 pid 存活
    backtest_tasks._remove_worker_pid(run_id)
    assert not backtest_tasks.is_run_active(run_id)


def test_is_run_active_with_dead_pid_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    pid_dir = backtest_tasks._worker_pid_dir()
    os.makedirs(pid_dir, exist_ok=True)
    with open(os.path.join(pid_dir, "99999.pid"), "w") as f:
        f.write("999999999")  # 几乎不可能存活的 pid
    assert not backtest_tasks.is_run_active(99999)


def test_worker_main_runs_and_cleans_pid(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_id = _new_run(repo)
    monkeypatch.setattr(backtest_tasks, "execute_run",
                        lambda rid: {"run_id": rid, "status": "succeeded"})
    assert worker_main(run_id) == 0
    assert not backtest_tasks._worker_pid_alive(run_id)


def test_worker_main_failure_marks_failed(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_id = _new_run(repo)

    def _boom(rid):
        raise RuntimeError("engine down")

    monkeypatch.setattr(backtest_tasks, "_build_repo", lambda: repo)
    monkeypatch.setattr(backtest_tasks, "execute_run", _boom)
    assert worker_main(run_id) == 1
    run = repo.get_run(run_id)
    assert run["summary"]["status"] == "failed"
    assert "engine down" in run["summary"]["error"]


def test_subprocess_spawn_failure_falls_back_inline(tmp_path, monkeypatch, repo):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_id = _new_run(repo)

    def _bad_popen(*a, **kw):
        raise OSError("no interpreter")

    monkeypatch.setattr(backtest_tasks.subprocess, "Popen", _bad_popen)
    monkeypatch.setattr(backtest_tasks, "execute_run",
                        lambda rid: {"run_id": rid, "status": "succeeded"})
    result = backtest_tasks.run_backtest_task(run_id, {}, "2024-01-01", "2024-01-31")
    assert result["status"] == "succeeded"
