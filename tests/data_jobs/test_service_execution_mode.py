from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.data_jobs.service import DataJobService

pytestmark = pytest.mark.module_data_jobs


class _InlineStore:
    def __init__(self):
        self.run = SimpleNamespace(id=201, status="pending", job_type="stock_basic", params_json={})

    def create_run(self, job_type, params):
        self.run.job_type = job_type
        self.run.params_json = params
        return self.run

    def update_run_status(self, run, status, progress=None, error_message=None):
        run.status = status
        if progress is not None:
            run.progress = progress
        return run

    def get_run(self, run_id):
        assert run_id == self.run.id
        return self.run


def test_submit_runs_inline_when_execution_mode_is_inline():
    store = _InlineStore()
    task = MagicMock()

    def _run_inline(run_id):
        assert run_id == store.run.id
        store.run.status = "success"
        return {"run_id": run_id, "status": "success"}

    task.side_effect = _run_inline
    task.delay = MagicMock()

    service = DataJobService(state_store=store, execution_mode="inline")

    with patch("app.services.data_jobs.service.run_data_job", task):
        run = service.submit("stock_basic", {})

    task.assert_called_once_with(run.id)
    task.delay.assert_not_called()
    assert run.status == "success"
