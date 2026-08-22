"""OpenAI 兼容的大模型流式客户端。

统一走 `<base_url>/v1/chat/completions` 协议，因此 DeepSeek、通义/OpenAI 兼容网关、
GLM、Moonshot、OpenAI 以及本地 Ollama（自带 /v1 兼容层）都可以直接使用，
只需在 .env 里配置 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY。

支持流式输出与 function calling（tool_calls 增量按 index 聚合）。
"""

import json
import logging
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """大模型调用失败（网络/HTTP/协议错误）。"""


class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.api_key = str(config.get('api_key') or '').strip()
        self.base_url = str(config.get('base_url') or 'https://api.deepseek.com').strip().rstrip('/')
        self.model = str(config.get('model') or 'deepseek-chat').strip()
        self.timeout = int(config.get('timeout') or 120)
        self.temperature = float(config.get('temperature', 0.3))
        self.max_tokens = int(config.get('max_tokens') or 4096)

    @property
    def configured(self) -> bool:
        """云端接口需要 api_key；本地端点（Ollama 等）无需 key。"""
        if not self.base_url or not self.model:
            return False
        if self.api_key:
            return True
        host = (urlparse(self.base_url).hostname or '').lower()
        return host in ('localhost', '127.0.0.1', '0.0.0.0', '::1')

    def endpoint(self) -> str:
        base = self.base_url.rstrip('/')
        if base.endswith('/chat/completions'):
            return base
        # 路径中已含 v1 段（OpenAI 官方、各类兼容网关）直接拼 chat/completions，
        # 否则（DeepSeek 裸域名、Ollama 根路径）补 /v1 前缀
        segments = [segment for segment in (urlparse(base).path or '').split('/') if segment]
        if 'v1' in segments:
            return f'{base}/chat/completions'
        return f'{base}/v1/chat/completions'

    def status_summary(self) -> Dict[str, Any]:
        return {
            'configured': self.configured,
            'base_url': self.base_url,
            'model': self.model,
            'has_api_key': bool(self.api_key),
        }

    # ------------------------------------------------------------------
    # 对外主入口：返回事件生成器
    #   {'type': 'delta',  'content': str}                     流式文本片段
    #   {'type': 'message','message': {...}}                   本轮完整 assistant 消息
    #   {'type': 'error',  'message': str}                     调用失败（终止）
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        if stream:
            yield from self._chat_stream(messages, tools)
        else:
            yield from self._chat_once(messages, tools)

    # ------------------------------------------------------------------
    # 非流式（测试与降级路径）

    def _chat_once(self, messages, tools) -> Iterator[Dict[str, Any]]:
        payload = self._build_payload(messages, tools, stream=False)
        response = self._post(payload)
        try:
            body = response.json()
            choice = body['choices'][0]
            message = choice['message']
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMClientError(f'大模型响应格式异常: {exc}') from exc

        normalized = {
            'role': 'assistant',
            'content': message.get('content') or None,
        }
        tool_calls = self._normalize_tool_calls(message.get('tool_calls'))
        if tool_calls:
            normalized['tool_calls'] = tool_calls
        yield {'type': 'message', 'message': normalized}

    # ------------------------------------------------------------------
    # 流式：SSE 增量解析

    def _chat_stream(self, messages, tools) -> Iterator[Dict[str, Any]]:
        payload = self._build_payload(messages, tools, stream=True)
        content_parts: List[str] = []
        tool_calls_acc: Dict[int, Dict[str, str]] = {}

        response = self._post(payload, stream=True)
        # OpenAI 兼容接口返回 UTF-8 JSON，但 Content-Type 通常不带 charset；
        # requests 会回退 latin-1 解码导致中文乱码，必须显式指定
        response.encoding = 'utf-8'
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith('data:'):
                    continue
                data = line[len('data:'):].strip()
                if data == '[DONE]':
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    logger.warning('忽略无法解析的流式片段: %s', data[:120])
                    continue

                choices = chunk.get('choices') or []
                if not choices:
                    continue
                delta = choices[0].get('delta') or {}

                piece = delta.get('content')
                if piece:
                    content_parts.append(piece)
                    yield {'type': 'delta', 'content': piece}

                for tc in delta.get('tool_calls') or []:
                    index = int(tc.get('index') or 0)
                    acc = tool_calls_acc.setdefault(index, {'id': '', 'name': '', 'arguments': ''})
                    if tc.get('id'):
                        acc['id'] = tc['id']
                    function = tc.get('function') or {}
                    if function.get('name'):
                        acc['name'] = acc['name'] or function['name']
                    if function.get('arguments'):
                        acc['arguments'] += function['arguments']
        finally:
            response.close()

        assembled: Dict[str, Any] = {
            'role': 'assistant',
            'content': ''.join(content_parts) or None,
        }
        if tool_calls_acc:
            assembled['tool_calls'] = [
                {
                    'id': acc['id'] or f'call_{index}',
                    'type': 'function',
                    'function': {'name': acc['name'], 'arguments': acc['arguments'] or '{}'},
                }
                for index, acc in sorted(tool_calls_acc.items())
                if acc['name']
            ]
        yield {'type': 'message', 'message': assembled}

    # ------------------------------------------------------------------
    # 内部工具

    def _build_payload(self, messages, tools, stream: bool) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'stream': stream,
        }
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'
        return payload

    def _post(self, payload: Dict[str, Any], stream: bool = False) -> requests.Response:
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        try:
            response = requests.post(
                self.endpoint(),
                headers=headers,
                json=payload,
                timeout=(10, self.timeout),
                stream=stream,
            )
        except requests.exceptions.Timeout as exc:
            raise LLMClientError(f'大模型请求超时（{self.timeout}s），可在 .env 调大 LLM_TIMEOUT') from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMClientError(f'无法连接大模型服务 {self.base_url}: {exc}') from exc
        except requests.exceptions.RequestException as exc:
            raise LLMClientError(f'大模型请求失败: {exc}') from exc

        if response.status_code != 200:
            excerpt = (response.text or '')[:300]
            response.close()
            hint = ''
            if response.status_code == 401:
                hint = '（请检查 .env 中的 LLM_API_KEY）'
            elif response.status_code == 404:
                hint = '（请检查 LLM_BASE_URL / LLM_MODEL 是否正确）'
            raise LLMClientError(
                f'大模型服务返回 {response.status_code}: {excerpt}{hint}'
            )
        return response

    @staticmethod
    def _normalize_tool_calls(raw_tool_calls) -> List[Dict[str, Any]]:
        normalized = []
        for tc in raw_tool_calls or []:
            function = tc.get('function') or {}
            if not function.get('name'):
                continue
            normalized.append(
                {
                    'id': tc.get('id') or 'call',
                    'type': 'function',
                    'function': {
                        'name': function['name'],
                        'arguments': function.get('arguments') or '{}',
                    },
                }
            )
        return normalized
