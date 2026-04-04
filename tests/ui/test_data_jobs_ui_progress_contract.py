from pathlib import Path


def test_data_jobs_page_contains_run_history_and_progress_blocks():
    html = Path("app/templates/data_management/index.html").read_text(encoding="utf-8")
    assert "dataJobHistory" in html
    assert "dataJobProgress" in html
