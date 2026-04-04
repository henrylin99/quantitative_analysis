from pathlib import Path


SCRIPTS = [
    "app/utils/daily_history_by_code.py",
    "app/utils/daily_history_by_date.py",
    "app/utils/moneyflow.py",
    "app/utils/moneyflow_ths.py",
    "app/utils/cyq_perf.py",
]


def test_scripts_use_job_env_helper():
    for rel in SCRIPTS:
        content = Path(rel).read_text(encoding="utf-8").lower()
        assert "from job_env import" in content


def test_scripts_do_not_truncate_tables():
    for rel in SCRIPTS:
        content = Path(rel).read_text(encoding="utf-8").lower()
        assert "truncate table" not in content


def test_scripts_do_not_hardcode_legacy_date():
    for rel in SCRIPTS:
        content = Path(rel).read_text(encoding="utf-8")
        assert "20250523" not in content
        assert "2025-05-27" not in content
