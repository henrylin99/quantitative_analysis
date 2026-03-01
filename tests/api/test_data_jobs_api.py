from flask import Flask
from types import SimpleNamespace
from unittest.mock import patch

from app.api.data_jobs_api import data_jobs_bp


def test_submit_endpoint_returns_job_id():
    app = Flask(__name__)
    app.register_blueprint(data_jobs_bp)
    client = app.test_client()

    fake_service = SimpleNamespace(
        submit=lambda job_type, params: SimpleNamespace(
            id=1, job_type=job_type, status="queued"
        )
    )

    with patch("app.api.data_jobs_api.get_data_job_service", return_value=fake_service):
        resp = client.post("/api/data-jobs/submit", json={"job_type": "stock_basic"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "run_id" in data
    assert data["success"] is True
