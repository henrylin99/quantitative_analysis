"""AI 智能工作台 API 契约测试：状态、会话 CRUD、SSE 流式对话。"""

from unittest.mock import patch

import pytest
from flask import Flask

from app.api.ai_assistant_api import ai_assistant_bp
from app.extensions import db
from app.models.ai_chat import AiChatSession


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        DATA_DIR=str(tmp_path),
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{tmp_path}/api_test.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AI_ASSISTANT_CONFIG={
            'api_key': 'k', 'base_url': 'https://fake', 'model': 'fake-model',
            'max_tool_iterations': 2,
        },
    )
    db.init_app(app)
    app.register_blueprint(ai_assistant_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_status_reports_llm_and_token_state(app, monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN', 'real')
    client = app.test_client()
    response = client.get('/api/ai-assistant/status')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['llm']['configured'] is True
    assert data['llm']['model'] == 'fake-model'
    assert data['tushare_token_configured'] is True
    tool_names = {tool['name'] for tool in data['tools']}
    assert 'query_data' in tool_names and 'build_wide_table' in tool_names


def test_session_crud_and_messages_flow(app):
    client = app.test_client()

    created = client.post('/api/ai-assistant/sessions', json={'title': '会话A'})
    assert created.status_code == 201
    session_id = created.get_json()['session']['id']

    listed = client.get('/api/ai-assistant/sessions')
    assert listed.get_json()['sessions'][0]['title'] == '会话A'

    missing = client.get(f'/api/ai-assistant/sessions/{session_id}/messages')
    assert missing.status_code == 200
    assert missing.get_json()['messages'] == []

    deleted = client.delete(f'/api/ai-assistant/sessions/{session_id}')
    assert deleted.status_code == 200
    assert client.delete(f'/api/ai-assistant/sessions/{session_id}').status_code == 404


class _FakeConfiguredService:
    """已配置的假服务：流式返回固定事件序列。"""

    class _Client:
        configured = True

    client = _Client()

    def __init__(self):
        pass

    def stream_chat(self, session_id, message, allow_actions=True):
        events = [
            {'type': 'session', 'session_id': 1, 'title': 't', 'created': True},
            {'type': 'token', 'content': '你好'},
            {'type': 'done', 'session_id': 1},
        ]
        for event in events:
            yield event


def test_chat_streams_sse_events(app):
    client = app.test_client()
    with patch('app.api.ai_assistant_api.AssistantService', _FakeConfiguredService):
        response = client.post(
            '/api/ai-assistant/chat',
            json={'message': '你好', 'allow_actions': False},
        )

    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    body = response.get_data(as_text=True)
    assert 'data: {"type": "session"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body


def test_chat_rejects_empty_message(app):
    response = app.test_client().post('/api/ai-assistant/chat', json={'message': '   '})
    assert response.status_code == 400


def test_chat_rejects_missing_session(app):
    class _Fake:
        class _Client:
            configured = True

        client = _Client()

        def __init__(self):
            pass

    with patch('app.api.ai_assistant_api.AssistantService', _Fake):
        response = app.test_client().post(
            '/api/ai-assistant/chat', json={'message': 'hi', 'session_id': 999}
        )
    assert response.status_code == 404


def test_chat_returns_400_when_llm_not_configured(app):
    original = app.config['AI_ASSISTANT_CONFIG']
    app.config['AI_ASSISTANT_CONFIG'] = dict(original, base_url='', model='', api_key='')
    try:
        # 使用真实 AssistantService（读取未配置的 config）
        response = app.test_client().post('/api/ai-assistant/chat', json={'message': 'hi'})
        assert response.status_code == 400
        assert 'LLM_API_KEY' in response.get_json()['error']
    finally:
        app.config['AI_ASSISTANT_CONFIG'] = original
