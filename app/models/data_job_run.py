from datetime import datetime

from app.extensions import db


class DataJobRun(db.Model):
    """Data download job run record."""

    __tablename__ = "data_job_run"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    progress = db.Column(db.Float, nullable=False, default=0.0)
    progress_message = db.Column(db.String(255))
    params_json = db.Column(db.JSON, nullable=False, default=dict)
    source_name = db.Column(db.String(64), index=True)
    source_mode = db.Column(db.String(32))
    snapshot_tag = db.Column(db.String(64))
    result_json = db.Column(db.JSON)
    error_message = db.Column(db.Text)
    log_text = db.Column(db.Text)
    queued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "params_json": self.params_json or {},
            "source_name": self.source_name,
            "source_mode": self.source_mode,
            "snapshot_tag": self.snapshot_tag,
            "result_json": self.result_json,
            "error_message": self.error_message,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
