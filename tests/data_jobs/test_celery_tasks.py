from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.data_jobs_tasks import run_data_job
from app.celery_app import celery

pytestmark = pytest.mark.module_data_jobs


def test_run_data_job_task_exists():
    assert callable(run_data_job)


def test_run_data_job_registered_in_celery():
    assert "data_jobs.run" in celery.tasks


def test_run_data_job_marks_success():
    fake_run = SimpleNamespace(
        id=10,
        job_type="stock_basic",
        status="queued",
        params_json={},
        result_json=None,
        error_message=None,
        source_name=None,
        source_mode=None,
        snapshot_tag=None,
    )
    fake_registry = MagicMock()
    fake_registry.get_job.return_value = SimpleNamespace(
        script_path="app/utils/stock_basic.py",
        source_name="tushare",
        source_mode="full",
    )
    fake_store = MagicMock()
    fake_store.get_run.return_value = fake_run
    fake_runner = MagicMock()
    fake_runner.run_script.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")

    @contextmanager
    def _ctx():
        yield

    fake_app = SimpleNamespace(app_context=lambda: _ctx())

    with patch("app.tasks.data_jobs_tasks._build_app", return_value=fake_app), patch(
        "app.tasks.data_jobs_tasks._build_registry", return_value=fake_registry
    ), patch("app.tasks.data_jobs_tasks._build_state_store", return_value=fake_store), patch(
        "app.tasks.data_jobs_tasks._build_runner", return_value=fake_runner
    ):
        result = run_data_job(10)

    assert result["status"] == "success"
    assert fake_runner.run_script.call_args.kwargs["params"] == {
        "source_name": "tushare",
        "source_mode": "full",
    }
    assert fake_store.update_run_status.call_args_list[0].args[1] == "running"
    assert fake_store.update_run_status.call_args_list[-1].args[1] == "success"
