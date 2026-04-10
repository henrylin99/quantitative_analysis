from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_feature_engineering


def test_train_model_response_does_not_include_demo_defaults(app):
    client = app.test_client()
    payload = {"model_id": "demo", "start_date": "2024-01-01", "end_date": "2024-01-31"}

    with patch("app.api.ml_factor_api.get_training_job_service") as get_service:
        get_service.return_value.submit_job.return_value = {
            "job_id": "job-123",
            "model_id": "demo",
            "status": "queued",
            "progress": 0.0,
            "step": "已加入训练队列",
            "logs": [],
        }

        response = client.post("/api/ml-factor/models/train", json=payload)

    assert response.status_code == 202
    data = response.get_json()
    assert "model_size" not in data
    assert "accuracy" not in data
    assert "loss" not in data
    assert "training_samples" not in data
    assert data["job_id"] == "job-123"
    assert data["status"] == "queued"
