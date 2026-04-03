from types import SimpleNamespace
from unittest.mock import patch

from app.services.data_jobs.service import DataJobService


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


def test_submit_creates_run_and_dispatches_task():
    store = DummyStore()
    service = DataJobService(state_store=store)

    with patch("app.services.data_jobs.service.run_data_job.delay") as delay:
        run = service.submit("stock_basic", {})

    delay.assert_called_once_with(run.id)
    assert run.status == "queued"
    assert store.updated is True
