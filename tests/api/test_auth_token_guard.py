"""API Token 门禁矩阵：/api/* 全方法鉴权、非 API 路径豁免、生产配置强制。"""
from unittest.mock import patch

import pytest


TOKEN = 'test-token-1234567890'


def _create_app(monkeypatch, token):
    import app as app_module

    if token is None:
        monkeypatch.delenv('API_AUTH_TOKEN', raising=False)
    else:
        monkeypatch.setenv('API_AUTH_TOKEN', token)
    with patch.object(app_module.socketio, 'init_app', return_value=None):
        return app_module.create_app('development')


@pytest.fixture()
def token_app(monkeypatch):
    return _create_app(monkeypatch, TOKEN)


@pytest.fixture()
def open_app(monkeypatch):
    return _create_app(monkeypatch, None)


def test_api_get_requires_token(token_app):
    client = token_app.test_client()
    resp = client.get('/api/data-jobs/jobs')
    assert resp.status_code == 401


def test_api_post_requires_token(token_app):
    client = token_app.test_client()
    resp = client.post('/api/data-jobs/submit', json={'job_type': 'stock_basic'})
    assert resp.status_code == 401


def test_api_rejects_wrong_token(token_app):
    client = token_app.test_client()
    resp = client.get('/api/data-jobs/jobs', headers={'X-API-Token': 'wrong'})
    assert resp.status_code == 401


def test_api_accepts_x_api_token(token_app):
    client = token_app.test_client()
    resp = client.get('/api/data-jobs/jobs', headers={'X-API-Token': TOKEN})
    assert resp.status_code == 200


def test_api_accepts_bearer_token(token_app):
    client = token_app.test_client()
    resp = client.get('/api/data-jobs/jobs', headers={'Authorization': f'Bearer {TOKEN}'})
    assert resp.status_code == 200


def test_non_api_path_not_guarded(token_app):
    """门禁只保护 /api/* 数据面；页面/静态资源不拦（拦截会连页面都打不开）。"""
    client = token_app.test_client()
    resp = client.get('/definitely-not-a-route')
    assert resp.status_code != 401


CORS_ORIGIN = 'http://localhost:5173'


def test_cors_preflight_options_bypasses_guard(token_app):
    """跨域预检请求（OPTIONS）不带 Token 是浏览器规范行为，必须放行给 Flask-CORS。"""
    client = token_app.test_client()
    resp = client.options('/api/text2sql/suggestions', headers={
        'Origin': CORS_ORIGIN,
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'x-api-token',
    })
    assert resp.status_code != 401
    # 预检响应由 Flask-CORS 补齐跨域头
    assert resp.headers.get('Access-Control-Allow-Origin') is not None


def test_actual_request_after_preflight_still_requires_token(token_app):
    """预检放行不等于放行实际请求：跨域 GET 无 Token 仍 401，带 Token 正常。"""
    client = token_app.test_client()
    resp = client.get('/api/text2sql/suggestions', headers={'Origin': CORS_ORIGIN})
    assert resp.status_code == 401

    resp = client.get(
        '/api/text2sql/suggestions',
        headers={'Origin': CORS_ORIGIN, 'X-API-Token': TOKEN},
    )
    assert resp.status_code == 200
    assert resp.headers.get('Access-Control-Allow-Origin') is not None


def test_without_token_env_api_stays_open(open_app):
    """未设置 API_AUTH_TOKEN（本机单人模式）保持原行为；生产配置会强制要求设置。"""
    client = open_app.test_client()
    resp = client.get('/api/data-jobs/jobs')
    assert resp.status_code == 200


def test_production_config_requires_api_token(monkeypatch):
    from config import config

    production = config['production']
    base = {'SECRET_KEY': 'real-secret', 'CORS_ORIGINS': 'https://example.com'}

    monkeypatch.setenv('API_AUTH_TOKEN', '')
    with pytest.raises(RuntimeError):
        production.validate(base)

    monkeypatch.setenv('API_AUTH_TOKEN', 'short')
    with pytest.raises(RuntimeError):
        production.validate(base)

    monkeypatch.setenv('API_AUTH_TOKEN', 'a' * 32)
    production.validate(base)  # 不抛即为通过
