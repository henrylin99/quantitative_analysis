import pytest

from app.services.data_jobs.runner import ScriptRunner

pytestmark = pytest.mark.module_data_jobs


def test_runner_rejects_unknown_script():
    runner = ScriptRunner()
    ok, msg = runner.validate_script("app/utils/not_exists.py")
    assert ok is False
    assert "not found" in msg


def test_runner_accepts_existing_script():
    runner = ScriptRunner()
    ok, msg = runner.validate_script("app/utils/stock_basic.py")
    assert ok is True
    assert msg == "ok"
