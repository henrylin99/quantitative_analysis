from app.services.data_jobs.registry import JobRegistry


def test_registry_contains_all_utils_jobs():
    registry = JobRegistry()
    jobs = registry.list_jobs()
    job_types = {job.job_type for job in jobs}

    assert len(jobs) >= 18
    assert "stock_basic" in job_types
    assert "min60" in job_types
    assert "income_statement" in job_types


def test_registry_visible_jobs_follow_whitelist():
    registry = JobRegistry()
    jobs = registry.list_visible_jobs()
    job_types = [job.job_type for job in jobs]

    assert len(job_types) == 8
    assert job_types == [
        "stock_basic",
        "trade_calendar",
        "stock_company",
        "daily_history_by_date",
        "daily_basic",
        "moneyflow",
        "stk_factor",
        "cyq_perf",
    ]
