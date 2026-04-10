import pytest

from app.models.data_job_run import DataJobRun

pytestmark = pytest.mark.module_data_jobs


def test_data_job_run_exposes_source_audit_fields():
    run = DataJobRun(
        job_type="daily_history_by_date",
        status="queued",
        params_json={},
        source_name="tushare",
        source_mode="incremental",
        snapshot_tag="2026-04-04",
        progress_message="准备执行",
    )

    payload = run.to_dict()

    assert payload["source_name"] == "tushare"
    assert payload["source_mode"] == "incremental"
    assert payload["snapshot_tag"] == "2026-04-04"
    assert payload["progress_message"] == "准备执行"
