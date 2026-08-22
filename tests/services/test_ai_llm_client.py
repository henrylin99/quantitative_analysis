"""AI 智能工作台 LLM 客户端单元测试（不发真实网络请求）。"""

import json
from unittest.mock import patch

import pytest

from app.services.ai.llm_client import LLMClient, LLMClientError


def _sse_response(chunks, status_code=200, text=''):
    """构造带 iter_lines 的假 requests.Response。"""
    lines = []
    for chunk in chunks:
        lines.append('data: ' + json.dumps(chunk, ensure_ascii=False))
    lines.append('data: [DONE]')

    class FakeResponse:
        def __init__(self):
            self.status_code = status_code
            self.text = text

        def iter_lines(self, decode_unicode=True):
            return iter(lines)

        def close(self):
            pass

    return FakeResponse()


def test_endpoint_appends_v1_unless_present():
    assert LLMClient({'base_url': 'https://api.deepseek.com'}).endpoint() == \
        'https://api.deepseek.com/v1/chat/completions'
    assert LLMClient({'base_url': 'http://localhost:11434/v1'}).endpoint() == \
        'http://localhost:11434/v1/chat/completions'
    # 路径中间已含 /v1 的兼容网关，不再重复追加 v1
    assert LLMClient({'base_url': 'https://gw.example.com/user-center/v1/model'}).endpoint() == \
        'https://gw.example.com/user-center/v1/model/chat/completions'
    assert LLMClient({'base_url': 'https://x.example.com/api/chat/completions'}).endpoint() == \
        'https://x.example.com/api/chat/completions'


def test_configured_requires_key_or_local_endpoint():
    # 云端接口（默认 DeepSeek）没有 api_key 视为未配置
    assert LLMClient({'base_url': '', 'model': 'm', 'api_key': ''}).configured is False
    assert LLMClient({'base_url': 'https://api.deepseek.com', 'model': '', 'api_key': ''}).configured is False
    # 配了 key 即可用
    assert LLMClient({'base_url': 'https://api.deepseek.com', 'model': 'm', 'api_key': 'sk-x'}).configured is True
    # 本地 Ollama 无需 key
    assert LLMClient({'base_url': 'http://localhost:11434', 'model': 'qwen', 'api_key': ''}).configured is True


def test_stream_accumulates_content_and_tool_calls():
    client = LLMClient({'base_url': 'https://fake', 'model': 'm', 'api_key': 'k'})
    chunks = [
        {'choices': [{'delta': {'content': '你好'}}]},
        {'choices': [{'delta': {
            'tool_calls': [
                {'index': 0, 'id': 'call_1', 'function': {'name': 'query_data', 'arguments': '{"sql":'}}
            ]
        }}]},
        {'choices': [{'delta': {
            'tool_calls': [
                {'index': 0, 'function': {'arguments': ' "SELECT 1"}'}}
            ]
        }}]},
    ]
    fake_response = _sse_response(chunks)
    with patch('app.services.ai.llm_client.requests.post', return_value=fake_response):
        events = list(client.chat([{'role': 'user', 'content': 'hi'}], tools=[{'type': 'function', 'function': {}}]))

    # 流式响应必须显式按 UTF-8 解码（否则中文会被 latin-1 损坏）
    assert fake_response.encoding == 'utf-8'

    deltas = [e['content'] for e in events if e['type'] == 'delta']
    assert deltas == ['你好']
    final = [e for e in events if e['type'] == 'message'][0]['message']
    assert final['content'] == '你好'
    assert final['tool_calls'] == [
        {
            'id': 'call_1',
            'type': 'function',
            'function': {'name': 'query_data', 'arguments': '{"sql": "SELECT 1"}'},
        }
    ]


def test_non_stream_normalizes_message():
    client = LLMClient({'base_url': 'https://fake', 'model': 'm', 'api_key': 'k'})

    class FakeResponse:
        status_code = 200
        text = ''

        def json(self):
            return {
                'choices': [
                    {
                        'message': {
                            'role': 'assistant',
                            'content': 'ok',
                            'tool_calls': [
                                {'id': 'c1', 'function': {'name': 'list_data_jobs', 'arguments': '{}'}}
                            ],
                        }
                    }
                ]
            }

        def close(self):
            pass

    with patch('app.services.ai.llm_client.requests.post', return_value=FakeResponse()):
        events = list(client.chat([{'role': 'user', 'content': 'hi'}], stream=False))

    assert events == [
        {
            'type': 'message',
            'message': {
                'role': 'assistant',
                'content': 'ok',
                'tool_calls': [
                    {'id': 'c1', 'type': 'function', 'function': {'name': 'list_data_jobs', 'arguments': '{}'}}
                ],
            },
        }
    ]


def test_http_error_raises_with_hint():
    client = LLMClient({'base_url': 'https://fake', 'model': 'm', 'api_key': 'bad'})

    class FakeResponse:
        status_code = 401
        text = '{"error": "auth"}'

        def close(self):
            pass

    with patch('app.services.ai.llm_client.requests.post', return_value=FakeResponse()):
        with pytest.raises(LLMClientError) as excinfo:
            list(client.chat([{'role': 'user', 'content': 'hi'}]))

    assert '401' in str(excinfo.value)
    assert 'LLM_API_KEY' in str(excinfo.value)
