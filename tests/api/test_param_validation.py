"""分页/数值查询参数校验：非法值、负数、超大值一律 400，不落 500。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.module_data_jobs


@pytest.mark.parametrize('bad', ['abc', '-1', '0', '999999'])
def test_data_jobs_list_rejects_bad_limit(app, bad):
    client = app.test_client()
    resp = client.get(f'/api/data-jobs/list?limit={bad}')
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_data_jobs_list_accepts_valid_limit(app):
    fake_service = SimpleNamespace(list_runs=lambda limit, status: [])
    with patch('app.api.data_jobs_api.get_data_job_service', return_value=fake_service):
        client = app.test_client()
        resp = client.get('/api/data-jobs/list?limit=10')
    assert resp.status_code == 200
    assert resp.get_json()['count'] == 0


@pytest.mark.parametrize('bad', ['abc', '-1', '0'])
def test_stock_list_rejects_bad_page(app, bad):
    client = app.test_client()
    resp = client.get(f'/api/stocks?page={bad}')
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 400


@pytest.mark.parametrize('bad', ['abc', '-1', '0', '999999'])
def test_stock_history_rejects_bad_limit(app, bad):
    client = app.test_client()
    resp = client.get(f'/api/stocks/000001.SZ/history?limit={bad}')
    assert resp.status_code == 400


@pytest.mark.parametrize('bad', ['abc', '-1', '0', '999999'])
def test_ai_sessions_rejects_bad_limit(app, bad):
    client = app.test_client()
    resp = client.get(f'/api/ai-assistant/sessions?limit={bad}')
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_realtime_monitor_rejects_bad_period_hours(app):
    client = app.test_client()
    resp = client.get('/api/realtime-analysis/monitor/anomalies?period_hours=abc')
    assert resp.status_code == 400
