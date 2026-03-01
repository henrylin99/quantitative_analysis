from datetime import datetime

from app.extensions import db


class DataJobCursor(db.Model):
    """Persisted cursor for incremental data jobs."""

    __tablename__ = "data_job_cursor"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(64), nullable=False, index=True)
    cursor_key = db.Column(db.String(128), nullable=False)
    cursor_value = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint("job_type", "cursor_key", name="uq_data_job_cursor_job_key"),
    )
