from app.tasks.data_jobs_tasks import run_data_job


def test_run_data_job_task_exists():
    assert callable(run_data_job)
