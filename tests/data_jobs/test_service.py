from types import SimpleNamespace
from unittest.mock import patch
import threading

import pytest

from app.services.data_jobs.service import DataJobService
from app.services.data_jobs.parquet_state_store import ParquetDataJobStateStore

pytestmark = pytest.mark.module_data_jobs


class DummyStore:
    def __init__(self):
        self.run = SimpleNamespace(id=101, status="pending", job_type="stock_basic", params_json={})
        self.updated = False

    def create_run(self, job_type, params):
        self.run.job_type = job_type
        self.run.params_json = params
        return self.run

    def update_run_status(self, run, status, progress=None, error_message=None):
        run.status = status
        self.updated = True
        return run


def test_submit_creates_run_and_dispatches_task_in_background_thread():
    """去 Celery 后默认本地执行：submit 开后台线程跑任务，立即返回 queued。"""
    store = DummyStore()
    service = DataJobService(state_store=store)
    started = threading.Event()

    def _fake_task(run_id):
        started.set()
        return {"run_id": run_id, "status": "success"}

    with patch("app.services.data_jobs.service.run_data_job", side_effect=_fake_task):
        run = service.submit("stock_basic", {})

    assert started.wait(timeout=5), "后台线程未在时限内执行任务"
    assert run.status == "queued"
    assert store.updated is True


def test_submit_with_legacy_celery_mode_still_dispatches_via_delay():
    """DATA_JOB_EXECUTION_MODE=celery 属 legacy 兼容值，.delay 已是本地同步壳。"""
    store = DummyStore()
    service = DataJobService(state_store=store, execution_mode="celery")

    with patch("app.services.data_jobs.service.run_data_job.delay") as delay:
        run = service.submit("stock_basic", {})

    delay.assert_called_once_with(run.id)
    assert run.status == "queued"


def test_service_uses_store_for_list_runs_and_get_run(tmp_path):
    store = ParquetDataJobStateStore(base_dir=str(tmp_path / "state"))
    run = store.create_run("stock_basic", {"start_date": "20260101"})
    store.update_run_status(run, "queued", progress=0.0, progress_message="任务已入队")
    service = DataJobService(state_store=store)

    runs = service.list_runs(limit=10, status="queued")
    fetched = service.get_run(run.id)

    assert len(runs) == 1
    assert runs[0].id == run.id
    assert fetched is not None
    assert fetched.id == run.id


def test_service_defaults_to_parquet_state_store():
    service = DataJobService()
    assert isinstance(service.state_store, ParquetDataJobStateStore)
