from app.services.data_jobs.registry import JobRegistry


def test_registry_contains_all_utils_jobs():
    registry = JobRegistry()
    jobs = registry.list_jobs()
    job_types = {job.job_type for job in jobs}

    assert len(jobs) >= 18
    assert "stock_basic" in job_types
    assert "min60" in job_types
    assert "income_statement" in job_types
