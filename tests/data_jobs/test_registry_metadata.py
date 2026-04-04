from app.services.data_jobs.registry import JobRegistry


def test_visible_jobs_include_display_metadata_for_guided_execution():
    registry = JobRegistry()
    jobs = registry.list_visible_jobs()
    first = next(job for job in jobs if job.job_type == "trade_calendar")
    history = next(job for job in jobs if job.job_type == "daily_history_by_date")

    assert first.display_name == "交易日历"
    assert first.recommended_order == 1
    assert history.display_name == "日线行情（按交易日）"
    assert history.recommended_order > first.recommended_order
    assert history.dependencies == ["trade_calendar"]
