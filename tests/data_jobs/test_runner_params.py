from unittest.mock import patch

from app.services.data_jobs.runner import ScriptRunner


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
