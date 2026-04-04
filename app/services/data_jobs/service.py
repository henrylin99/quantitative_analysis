from typing import Any, Dict, Optional

from app.extensions import db
from app.models.data_job_run import DataJobRun
from app.services.data_jobs.registry import JobRegistry
from app.services.data_jobs.state_store import DataJobStateStore
from app.tasks.data_jobs_tasks import run_data_job

try:
    from flask import current_app
except Exception:  # pragma: no cover
    current_app = None


def _resolve_execution_mode(explicit_mode: Optional[str] = None) -> str:
    if explicit_mode:
        return explicit_mode

    try:
        if current_app:
            mode = current_app.config.get("DATA_JOB_EXECUTION_MODE")
            if mode:
                return str(mode).lower()
    except Exception:
        pass

    return "celery"


class DataJobService:
    """Facade for data job submission and querying."""

    def __init__(
        self,
        registry: Optional[JobRegistry] = None,
        state_store: Optional[DataJobStateStore] = None,
        execution_mode: Optional[str] = None,
    ):
        self.registry = registry or JobRegistry()
        self.state_store = state_store or DataJobStateStore(db.session)
        self.execution_mode = _resolve_execution_mode(execution_mode)

    def submit(self, job_type: str, params: Optional[Dict[str, Any]] = None) -> DataJobRun:
        self.registry.get_job(job_type)
        params = params or {}
        find_active_duplicate = getattr(self.state_store, "find_active_duplicate", None)
        if callable(find_active_duplicate):
            duplicate_run = find_active_duplicate(job_type, params)
            if duplicate_run is not None:
                raise ValueError(f"duplicate running job: {duplicate_run.id}")

        run = self.state_store.create_run(job_type, params)
        run = self.state_store.update_run_status(run, "queued", progress=0.0)

        if self.execution_mode == "inline":
            run_data_job(run.id)
            refreshed = getattr(self.state_store, "get_run", None)
            if callable(refreshed):
                latest = refreshed(run.id)
                if latest is not None:
                    return latest
            return run

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
