from flask import Flask
from types import SimpleNamespace
from unittest.mock import patch

from app.api.data_jobs_api import data_jobs_bp


class _FakeService:
    def __init__(self):
        self.called = None

    def list_runs(self, limit, status):
        self.called = {"limit": limit, "status": status}
        return [SimpleNamespace(to_dict=lambda: {"status": status})]


def test_list_runs_supports_status_filter():
    app = Flask(__name__)
    app.register_blueprint(data_jobs_bp)
    client = app.test_client()

    fake_service = _FakeService()

    with patch("app.api.data_jobs_api.get_data_job_service", return_value=fake_service):
        resp = client.get("/api/data-jobs/list?status=failed&limit=10")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert fake_service.called == {"limit": 10, "status": "failed"}
    assert all(run["status"] == "failed" for run in data["runs"])
