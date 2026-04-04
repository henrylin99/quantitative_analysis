from pathlib import Path


def test_data_jobs_page_contains_run_history_and_progress_blocks():
    html = Path("app/templates/data_management/index.html").read_text(encoding="utf-8")
    assert "dataJobHistory" in html
    assert "dataJobProgress" in html


def test_data_jobs_time_display_uses_shanghai_timezone():
    script = Path("app/static/js/data_jobs.js").read_text(encoding="utf-8")

    assert 'timeZone: "Asia/Shanghai"' in script
