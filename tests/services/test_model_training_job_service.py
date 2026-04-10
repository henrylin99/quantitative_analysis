import pytest

from app.services.model_training_job_service import ModelTrainingJobService

pytestmark = pytest.mark.module_ml_model


def test_training_job_service_exposes_snapshot_with_progress_and_logs():
    snapshots = {
        "job-123": {
            "job_id": "job-123",
            "model_id": "demo",
            "status": "running",
            "progress": 25.0,
            "logs": ["preparing data"],
        }
    }

    service = ModelTrainingJobService(job_store=snapshots)
    snapshot = service.get_job_snapshot("job-123")

    assert snapshot["job_id"] == "job-123"
    assert snapshot["status"] == "running"
    assert snapshot["progress"] == 25.0
    assert snapshot["logs"] == ["preparing data"]
