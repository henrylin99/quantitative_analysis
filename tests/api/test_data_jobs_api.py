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


def test_jobs_endpoint_uses_visible_only_by_default():
    app = Flask(__name__)
    app.register_blueprint(data_jobs_bp)
    client = app.test_client()

    fake_job = SimpleNamespace(
        job_type="stock_basic",
        group="基础资料",
        script_path="app/utils/stock_basic.py",
        display_name="股票基础资料",
        description="下载股票基础信息",
        recommended_order=2,
        dependencies=[],
    )
    fake_service = SimpleNamespace(list_job_definitions=lambda visible_only=True: [fake_job] if visible_only else [])

    with patch("app.api.data_jobs_api.get_data_job_service", return_value=fake_service):
        resp = client.get("/api/data-jobs/jobs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["jobs"][0]["job_type"] == "stock_basic"
    assert data["jobs"][0]["display_name"] == "股票基础资料"


def test_jobs_endpoint_can_include_hidden():
    app = Flask(__name__)
    app.register_blueprint(data_jobs_bp)
    client = app.test_client()

    visible_job = SimpleNamespace(job_type="stock_basic", group="基础资料", script_path="app/utils/stock_basic.py", display_name="股票基础资料", description="", recommended_order=2, dependencies=[])
    hidden_job = SimpleNamespace(job_type="min5", group="分钟行情", script_path="app/utils/min5.py", display_name="5 分钟行情", description="", recommended_order=20, dependencies=[])

    def _list_job_definitions(visible_only=True):
        return [visible_job] if visible_only else [visible_job, hidden_job]

    fake_service = SimpleNamespace(list_job_definitions=_list_job_definitions)

    with patch("app.api.data_jobs_api.get_data_job_service", return_value=fake_service):
        resp = client.get("/api/data-jobs/jobs?include_hidden=true")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2
