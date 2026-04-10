from unittest.mock import MagicMock

import pytest

from app.services.data_jobs.state_store import DataJobStateStore

pytestmark = pytest.mark.module_data_jobs


def test_create_run_sets_pending_status():
    session = MagicMock()
    store = DataJobStateStore(session)

    run = store.create_run("stock_basic", {"start_date": "20250101"})

    assert run.status == "pending"
    assert run.job_type == "stock_basic"
    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_update_run_status_persists_progress_message():
    session = MagicMock()
    run = MagicMock(
        status="pending",
        progress=0.0,
        error_message=None,
        started_at=None,
        finished_at=None,
    )
    store = DataJobStateStore(session)

    store.update_run_status(run, "running", progress=15.0, progress_message="下载中")

    assert run.status == "running"
    assert run.progress == 15.0
    assert run.progress_message == "下载中"
    session.commit.assert_called_once()
