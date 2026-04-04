from pathlib import Path


def test_data_management_page_contains_data_jobs_entry():
    html = Path("app/templates/data_management/index.html").read_text(encoding="utf-8")

    assert "日频数据中心" in html
    assert "data-jobs-panel" in html


def test_realtime_page_no_longer_contains_data_jobs_entry():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "日频数据中心" not in html
    assert "data-jobs-panel" not in html
