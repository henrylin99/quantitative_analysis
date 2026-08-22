"""AI 智能工作台对话编排测试：工具调用循环、事件流、会话持久化、模式与迭代上限。"""

import pytest
from flask import Flask

from app.extensions import db
from app.models.ai_chat import AiChatMessage, AiChatSession
from app.services.ai.assistant_service import AssistantError, AssistantService
from app.services.ai.llm_client import LLMClient


class FakeClient:
    """脚本化的大模型客户端：每次 chat 弹出一组事件。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.model = 'fake-model'

    @property
    def configured(self):
        return True

    def chat(self, messages, tools=None, stream=True):
        self.calls.append(([dict(m) for m in messages], tools))
        events = self.responses.pop(0)
        return iter(list(events))


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        DATA_DIR=str(tmp_path),
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{tmp_path}/ai_test.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AI_ASSISTANT_CONFIG={
            'api_key': 'k', 'base_url': 'https://fake', 'model': 'fake-model',
            'max_tool_iterations': 2,
        },
    )
    from app.extensions import db as _db

    _db.init_app(app)
    with app.app_context():
        AssistantService._tables_ready = False
        db.create_all()
        yield app
        db.session.remove()
        AssistantService._tables_ready = False


def _tool_call_event(call_id, name, arguments):
    return {
        'type': 'message',
        'message': {
            'role': 'assistant',
            'content': '我先查询一下',
            'tool_calls': [
                {'id': call_id, 'type': 'function',
                 'function': {'name': name, 'arguments': arguments}}
            ],
        },
    }


def _final_event(content):
    return {'type': 'message', 'message': {'role': 'assistant', 'content': content}}


def test_conversation_with_tool_call_persists_messages(app):
    client = FakeClient(
        [
            [{'type': 'delta', 'content': '我先'}, {'type': 'delta', 'content': '查询一下'}, _tool_call_event('call_1', 'list_data_jobs', '{}')],
            [_final_event('系统支持 20 个数据任务。')],
        ]
    )
    service = AssistantService(client=client)

    events = list(service.stream_chat(None, '系统有哪些数据任务？'))

    types = [e['type'] for e in events]
    assert 'session' in types
    assert 'token' in types
    assert types.count('tool_call') == 1
    assert types.count('tool_result') == 1
    assert types[-1] == 'done'

    tool_result = next(e for e in events if e['type'] == 'tool_result')
    assert tool_result['name'] == 'list_data_jobs'
    assert tool_result['ok'] is True

    session_id = next(e for e in events if e['type'] == 'session')['session_id']
    roles = [(m.role, m.tool_name) for m in AiChatMessage.query.filter_by(session_id=session_id).all()]
    assert ('user', None) in roles
    assert ('tool', 'list_data_jobs') in roles
    assert ('assistant', None) in roles


def test_history_replay_excludes_tool_messages(app):
    client = FakeClient(
        [
            [_tool_call_event('c1', 'list_data_jobs', '{}')],
            [_final_event('第一轮回答')],
            [_final_event('第二轮回答')],
        ]
    )
    service = AssistantService(client=client)

    first = list(service.stream_chat(None, '第一问'))
    session_id = next(e for e in first if e['type'] == 'session')['session_id']
    list(service.stream_chat(session_id, '第二问'))

    second_messages, _tools = client.calls[2]
    roles = [m['role'] for m in second_messages]
    # system + 第一问(user) + 第一轮回答(assistant) + 第二问(user)，工具记录不回放
    assert roles == ['system', 'user', 'assistant', 'user']
    assert '第二问' in second_messages[-1]['content']
    system_prompt = second_messages[0]['content']
    assert 'stock_business' in system_prompt
    assert '操作模式' in system_prompt


def test_readonly_mode_blocks_action_tools(app):
    client = FakeClient(
        [
            [_tool_call_event('c1', 'run_data_job', '{"job_type": "daily_basic"}')],
            [_final_event('当前为只读模式，无法执行该操作。')],
        ]
    )
    service = AssistantService(client=client)

    events = list(service.stream_chat(None, '帮我更新数据', allow_actions=False))

    tool_result = next(e for e in events if e['type'] == 'tool_result')
    assert tool_result['ok'] is False
    assert '只读模式' in tool_result['result']['error']

    # 只读模式下传给模型的工具列表不含动作工具
    _, tools = client.calls[0]
    tool_names = {t['function']['name'] for t in tools}
    assert 'query_data' in tool_names
    assert 'run_data_job' not in tool_names

    # 系统提示词声明只读模式
    system_prompt = client.calls[0][0][0]['content']
    assert '只读模式' in system_prompt


def test_max_iterations_guard_emits_error(app):
    endless = [[_tool_call_event(f'c{i}', 'list_data_jobs', '{}')] for i in range(5)]
    client = FakeClient(endless)
    service = AssistantService(client=client)

    events = list(service.stream_chat(None, '不停调用工具'))

    assert any(e['type'] == 'error' and '最大工具调用轮数' in e['message'] for e in events)
    assert not any(e['type'] == 'done' for e in events)
    assert len(client.calls) == 2  # max_tool_iterations=2


def test_unconfigured_client_raises(app):
    service = AssistantService(client=LLMClient({'base_url': '', 'model': '', 'api_key': ''}))
    with pytest.raises(AssistantError) as excinfo:
        list(service.stream_chat(None, '你好'))
    assert 'LLM_API_KEY' in str(excinfo.value)


def test_session_management_roundtrip(app):
    service = AssistantService(client=FakeClient([]))

    created = service.create_session('测试会话')
    assert created.title == '测试会话'
    assert service.list_sessions()[0]['id'] == created.id

    db.session.add(AiChatMessage(session_id=created.id, role='user', content='hi'))
    db.session.commit()
    messages = service.get_messages(created.id)
    assert len(messages) == 1 and messages[0]['content'] == 'hi'

    with pytest.raises(AssistantError):
        service.get_messages(99999)

    assert service.delete_session(created.id) is True
    assert service.delete_session(created.id) is False
    assert AiChatSession.query.count() == 0
