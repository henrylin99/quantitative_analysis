from flask import Flask
from types import SimpleNamespace
from unittest.mock import patch

from app.api.data_jobs_api import data_jobs_bp


def test_submit_unknown_job_returns_400():
    app = Flask(__name__)
    app.register_blueprint(data_jobs_bp)
    client = app.test_client()

    def _submit(_job_type, _params):
        raise KeyError("unknown job type: unknown_job")

    fake_service = SimpleNamespace(submit=_submit)

    with patch("app.api.data_jobs_api.get_data_job_service", return_value=fake_service):
        resp = client.post("/api/data-jobs/submit", json={"job_type": "unknown_job"})

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
