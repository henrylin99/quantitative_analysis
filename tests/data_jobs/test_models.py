import pytest

from app.models.data_job_run import DataJobRun
from app.models.data_job_cursor import DataJobCursor

pytestmark = pytest.mark.module_data_jobs


def test_data_job_run_has_status_field():
    assert DataJobRun.__tablename__ == "data_job_run"
    assert hasattr(DataJobRun, "status")
    assert hasattr(DataJobRun, "source_name")
    assert hasattr(DataJobRun, "source_mode")
    assert hasattr(DataJobRun, "snapshot_tag")
    assert hasattr(DataJobRun, "progress_message")


def test_data_job_cursor_has_cursor_value_field():
    assert DataJobCursor.__tablename__ == "data_job_cursor"
    assert hasattr(DataJobCursor, "cursor_value")
