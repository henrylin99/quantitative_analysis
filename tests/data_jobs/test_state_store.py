from types import SimpleNamespace

import pytest

from app.services.data_jobs.state_store import DataJobStateStore

pytestmark = pytest.mark.module_data_jobs


class _FakeStateStore:
    def __init__(self):
        self.calls = []

    def create_run(self, **kwargs):
        self.calls.append(("create_run", kwargs))
        return SimpleNamespace(**kwargs)

    def find_active_duplicate(self, job_type, params):
        self.calls.append(("find_active_duplicate", job_type, params))
        return None

    def get_run(self, run_id):
        self.calls.append(("get_run", run_id))
        return SimpleNamespace(id=run_id)

    def update_run_status(self, run, status, progress=None, error_message=None, progress_message=None):
        self.calls.append(("update_run_status", run, status, progress, error_message, progress_message))
        return SimpleNamespace(id=run.id, status=status)

    def save_run(self, run):
        self.calls.append(("save_run", run))
        return run

    def upsert_cursor(self, job_type, cursor_key, cursor_value):
        self.calls.append(("upsert_cursor", job_type, cursor_key, cursor_value))
        return SimpleNamespace(job_type=job_type, cursor_key=cursor_key, cursor_value=cursor_value)

    def list_runs(self, limit=50, status=None):
        self.calls.append(("list_runs", limit, status))
        return [SimpleNamespace(id=1)]


def test_state_store_delegates_to_parquet_backend():
    backend = _FakeStateStore()
    store = DataJobStateStore(state_store=backend)

    run = store.create_run("stock_basic", {"start_date": "20260101"}, source_name="tushare")
    assert run.job_type == "stock_basic"

    assert store.find_active_duplicate("stock_basic", {"start_date": "20260101"}) is None
    assert store.get_run(7).id == 7

    updated = store.update_run_status(SimpleNamespace(id=7), "running", progress=10.0, progress_message="处理中")
    assert updated.status == "running"

    assert store.save_run(SimpleNamespace(id=8)).id == 8
    assert store.upsert_cursor("stock_basic", "daily", "2026-06-05").cursor_key == "daily"
    assert len(store.list_runs(limit=5, status="failed")) == 1

    assert [call[0] for call in backend.calls] == [
        "create_run",
        "find_active_duplicate",
        "get_run",
        "update_run_status",
        "save_run",
        "upsert_cursor",
        "list_runs",
    ]
