from typing import Any, Dict, Optional

from app.extensions import db
from app.models.data_job_run import DataJobRun
from app.services.data_jobs.registry import JobRegistry
from app.services.data_jobs.state_store import DataJobStateStore
from app.tasks.data_jobs_tasks import run_data_job


class DataJobService:
    """Facade for data job submission and querying."""

    def __init__(self, registry: Optional[JobRegistry] = None, state_store: Optional[DataJobStateStore] = None):
        self.registry = registry or JobRegistry()
        self.state_store = state_store or DataJobStateStore(db.session)

    def submit(self, job_type: str, params: Optional[Dict[str, Any]] = None) -> DataJobRun:
        self.registry.get_job(job_type)
        run = self.state_store.create_run(job_type, params or {})
        run = self.state_store.update_run_status(run, "queued", progress=0.0)
        run_data_job.delay(run.id)
        return run

    def retry(self, run_id: int) -> DataJobRun:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"job run not found: {run_id}")
        return self.submit(run.job_type, run.params_json or {})

    def list_job_definitions(self, visible_only: bool = True):
        if visible_only:
            return self.registry.list_visible_jobs()
        return self.registry.list_jobs()

    def list_runs(self, limit: int = 50, status: Optional[str] = None):
        query = DataJobRun.query.order_by(DataJobRun.id.desc())
        if status:
            query = query.filter(DataJobRun.status == status)
        return query.limit(limit).all()

    def get_run(self, run_id: int) -> Optional[DataJobRun]:
        return DataJobRun.query.filter_by(id=run_id).first()
