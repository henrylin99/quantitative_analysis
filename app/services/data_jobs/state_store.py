from datetime import datetime
from typing import Any, Dict, Optional

from app.models.data_job_cursor import DataJobCursor
from app.models.data_job_run import DataJobRun


class DataJobStateStore:
    """Persistence wrapper for data job run state."""

    def __init__(self, session):
        self.session = session

    def create_run(self, job_type: str, params: Dict[str, Any]) -> DataJobRun:
        run = DataJobRun(job_type=job_type, params_json=params or {}, status="pending")
        self.session.add(run)
        self.session.commit()
        return run

    def update_run_status(
        self,
        run: DataJobRun,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> DataJobRun:
        run.status = status
        if progress is not None:
            run.progress = progress
        if error_message is not None:
            run.error_message = error_message
        if status == "running" and run.started_at is None:
            run.started_at = datetime.utcnow()
        if status in {"success", "failed", "cancelled"}:
            run.finished_at = datetime.utcnow()
        self.session.commit()
        return run

    def upsert_cursor(self, job_type: str, cursor_key: str, cursor_value: str) -> DataJobCursor:
        cursor = (
            self.session.query(DataJobCursor)
            .filter_by(job_type=job_type, cursor_key=cursor_key)
            .first()
        )
        if cursor is None:
            cursor = DataJobCursor(job_type=job_type, cursor_key=cursor_key, cursor_value=cursor_value)
            self.session.add(cursor)
        else:
            cursor.cursor_value = cursor_value
        self.session.commit()
        return cursor
