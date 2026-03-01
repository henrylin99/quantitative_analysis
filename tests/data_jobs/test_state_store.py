from unittest.mock import MagicMock

from app.services.data_jobs.state_store import DataJobStateStore


def test_create_run_sets_pending_status():
    session = MagicMock()
    store = DataJobStateStore(session)

    run = store.create_run("stock_basic", {"start_date": "20250101"})

    assert run.status == "pending"
    assert run.job_type == "stock_basic"
    session.add.assert_called_once()
    session.commit.assert_called_once()
