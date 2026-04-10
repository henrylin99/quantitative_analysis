from unittest.mock import patch

import pytest

from app.services.data_jobs.runner import ScriptRunner

pytestmark = pytest.mark.module_data_jobs


def test_runner_injects_date_params_into_env(tmp_path):
    script = tmp_path / "task.py"
    script.write_text("print('ok')", encoding="utf-8")

    runner = ScriptRunner(project_root=tmp_path)

    with patch("subprocess.run") as mock_run:
        runner.run_script(
            "task.py",
            params={"start_date": "2026-02-13", "end_date": "2026-03-01"},
        )

    env = mock_run.call_args.kwargs["env"]
    assert env["DATA_JOB_START_DATE"] == "2026-02-13"
    assert env["DATA_JOB_END_DATE"] == "2026-03-01"


def test_runner_injects_audit_params_into_env(tmp_path):
    script = tmp_path / "task.py"
    script.write_text("print('ok')", encoding="utf-8")

    runner = ScriptRunner(project_root=tmp_path)

    with patch("subprocess.run") as mock_run:
        runner.run_script(
            "task.py",
            params={
                "source_name": "tushare",
                "source_mode": "incremental",
                "snapshot_tag": "2026-04-04",
            },
        )

    env = mock_run.call_args.kwargs["env"]
    assert env["DATA_JOB_SOURCE_NAME"] == "tushare"
    assert env["DATA_JOB_SOURCE_MODE"] == "incremental"
    assert env["DATA_JOB_SNAPSHOT_TAG"] == "2026-04-04"
