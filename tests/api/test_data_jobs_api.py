"""数据任务 API 合约：真实 Flask app fixture + 服务边界 mock。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_data_jobs


def test_submit_endpoint_returns_job_id(app):
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


def test_jobs_endpoint_uses_visible_only_by_default(app):
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


def test_jobs_endpoint_can_include_hidden(app):
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


def test_get_run_endpoint_returns_audit_fields(app):
    client = app.test_client()

    fake_run = SimpleNamespace(
        to_dict=lambda: {
            "id": 9,
            "job_type": "daily_basic",
            "status": "running",
            "progress": 35.0,
            "progress_message": "准备下载",
            "source_name": "tushare",
            "source_mode": "incremental",
            "snapshot_tag": "2026-04-04",
        }
    )
    fake_service = SimpleNamespace(get_run=lambda run_id: fake_run)

    with patch("app.api.data_jobs_api.get_data_job_service", return_value=fake_service):
        resp = client.get("/api/data-jobs/9")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["run"]["progress_message"] == "准备下载"
    assert data["run"]["source_name"] == "tushare"
