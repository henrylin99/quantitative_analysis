from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_ml_model


def test_train_model_submits_backend_job(app):
    client = app.test_client()
    payload = {"model_id": "demo", "start_date": "2024-01-01", "end_date": "2024-01-31"}

    with patch("app.api.ml_factor_api.get_training_job_service") as get_service:
        get_service.return_value.submit_job.return_value = {
            "job_id": "job-123",
            "model_id": "demo",
            "status": "queued",
            "progress": 0.0,
            "logs": [],
        }

        response = client.post("/api/ml-factor/models/train", json=payload)

    assert response.status_code == 202
    data = response.get_json()
    assert data["success"] is True
    assert data["job_id"] == "job-123"
    assert data["status"] == "queued"
    assert "metrics" not in data


def test_train_job_status_endpoint_returns_snapshot(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_training_job_service") as get_service:
        get_service.return_value.get_job_snapshot.return_value = {
            "job_id": "job-123",
            "model_id": "demo",
            "status": "running",
            "progress": 35.0,
            "logs": ["preparing data"],
        }

        response = client.get("/api/ml-factor/models/train-jobs/job-123")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["job"]["job_id"] == "job-123"
    assert data["job"]["status"] == "running"


def test_training_date_range_endpoint_returns_suggestion(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_ml_manager") as get_manager:
        get_manager.return_value.suggest_training_date_range.return_value = {
            "model_id": "demo",
            "start_date": "2024-06-10",
            "end_date": "2024-06-10",
            "target_type": "return_1d",
            "target_period": 1,
            "message": "已建议最近可计算未来收益的训练日期: 2024-06-10",
        }

        response = client.get("/api/ml-factor/models/demo/training-date-range")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["date_range"]["start_date"] == "2024-06-10"
    assert data["date_range"]["end_date"] == "2024-06-10"
