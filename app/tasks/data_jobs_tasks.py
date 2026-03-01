from app.celery_app import celery


@celery.task(name="data_jobs.run")
def run_data_job(run_id: int):
    """Background task entrypoint for data jobs."""

    return {"run_id": run_id, "status": "queued"}
