"""大模型流式客户端（多协议）。

- openai（默认）：OpenAI 兼容 `<base_url>/v1/chat/completions` 协议，
  DeepSeek、通义/OpenAI 兼容网关、GLM、Moonshot、OpenAI、智谱均可直接使用；
- ollama：本地 Ollama（自带 /v1 兼容层，协议同 openai，无需 api_key）；
- anthropic：Claude 原生 `/v1/messages` 协议（x-api-key 头，system 独立字段，
  工具调用为 tool_use / input_json_delta，内部归一为 OpenAI tool_calls 形态）。

provider 由 .env 的 LLM_PROVIDER 指定，未指定时按 base_url 自动推断。
"""

import json
import logging
import re
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
        self.provider = self._resolve_provider(str(config.get('provider') or '').strip().lower())
        self.timeout = int(config.get('timeout') or 120)
        self.temperature = float(config.get('temperature', 0.3))
        self.max_tokens = int(config.get('max_tokens') or 4096)

    def _resolve_provider(self, provider: str) -> str:
        if provider in ('openai', 'ollama', 'anthropic'):
            return provider
        # 未指定时按 base_url 推断：anthropic 域名 → claude；本地地址 → ollama；
        # 其余一律 openai 兼容（覆盖绝大多数国内外网关）
        host = (urlparse(self.base_url).hostname or '').lower()
        if 'anthropic.com' in host:
            return 'anthropic'
        if host in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
            return 'ollama'
        return 'openai'

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
        # 路径中已含版本段（v1/v4 等，OpenAI 官方、智谱、各类兼容网关）直接拼
        # chat/completions，否则（DeepSeek 裸域名、Ollama 根路径）补 /v1 前缀
        segments = [segment for segment in (urlparse(base).path or '').split('/') if segment]
        if any(re.fullmatch(r'v\d+', segment) for segment in segments):
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
        if self.provider == 'anthropic':
            yield from self._anthropic_chat_once(messages, tools)
            return
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
        if self.provider == 'anthropic':
            yield from self._anthropic_chat_stream(messages, tools)
            return
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
    # Anthropic Claude 原生协议（/v1/messages）
    #   请求：system 抽独立字段；tools 转成 {name,description,input_schema}；
    #   响应：content 块列表（text / tool_use），tool_use 归一为 OpenAI tool_calls。

    _ANTHROPIC_VERSION = '2023-06-01'

    def _anthropic_endpoint(self) -> str:
        base = self.base_url.rstrip('/')
        if base.endswith('/messages'):
            return base
        segments = [s for s in (urlparse(base).path or '').split('/') if s]
        if segments and re.fullmatch(r'v\d+', segments[-1]):
            return f'{base}/messages'
        return f'{base}/v1/messages'

    def _anthropic_payload(self, messages, tools, stream: bool) -> Dict[str, Any]:
        system_texts = []
        normalized = []
        for message in messages:
            role = message.get('role')
            content = message.get('content') or ''
            if role == 'system':
                if content:
                    system_texts.append(str(content))
            else:
                normalized.append({'role': role or 'user', 'content': content})
        payload: Dict[str, Any] = {
            'model': self.model,
            'messages': normalized,
            'max_tokens': self.max_tokens,
            'stream': stream,
        }
        if system_texts:
            payload['system'] = '\n'.join(system_texts)
        if tools:
            payload['tools'] = [
                {
                    'name': t['function']['name'],
                    'description': t['function'].get('description') or '',
                    'input_schema': t['function'].get('parameters') or {'type': 'object', 'properties': {}},
                }
                for t in tools
                if t.get('type') == 'function' and (t.get('function') or {}).get('name')
            ]
            payload['tool_choice'] = {'type': 'auto'}
        return payload

    def _anthropic_post(self, payload: Dict[str, Any], stream: bool = False) -> requests.Response:
        headers = {
            'Content-Type': 'application/json',
            'anthropic-version': self._ANTHROPIC_VERSION,
        }
        if self.api_key:
            headers['x-api-key'] = self.api_key
        try:
            response = requests.post(
                self._anthropic_endpoint(),
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
            raise LLMClientError(f'大模型服务返回 {response.status_code}: {excerpt}{hint}')
        return response

    def _anthropic_chat_once(self, messages, tools) -> Iterator[Dict[str, Any]]:
        payload = self._anthropic_payload(messages, tools, stream=False)
        response = self._anthropic_post(payload)
        try:
            body = response.json()
            blocks = body.get('content') or []
        except ValueError as exc:
            raise LLMClientError(f'大模型响应格式异常: {exc}') from exc
        yield {'type': 'message', 'message': self._anthropic_assemble(blocks)}

    def _anthropic_chat_stream(self, messages, tools) -> Iterator[Dict[str, Any]]:
        payload = self._anthropic_payload(messages, tools, stream=True)
        response = self._anthropic_post(payload, stream=True)
        response.encoding = 'utf-8'
        blocks: List[Dict[str, Any]] = []
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith('data:'):
                    continue
                data = line[len('data:'):].strip()
                try:
                    event = json.loads(data)
                except ValueError:
                    logger.warning('忽略无法解析的流式片段: %s', data[:120])
                    continue
                etype = event.get('type')
                if etype == 'content_block_start':
                    blocks.append(event.get('content_block') or {})
                elif etype == 'content_block_delta':
                    delta = event.get('delta') or {}
                    piece = delta.get('text')
                    if piece:
                        text_block = next((b for b in reversed(blocks) if b.get('type') == 'text'), None)
                        if text_block is not None:
                            text_block['text'] = (text_block.get('text') or '') + piece
                        else:
                            blocks.append({'type': 'text', 'text': piece})
                        yield {'type': 'delta', 'content': piece}
                    partial = delta.get('partial_json')
                    if partial:
                        tool_block = next((b for b in reversed(blocks) if b.get('type') == 'tool_use'), None)
                        if tool_block is not None:
                            tool_block['input_json'] = (tool_block.get('input_json') or '') + partial
                elif etype == 'message_stop':
                    break
        finally:
            response.close()
        yield {'type': 'message', 'message': self._anthropic_assemble(blocks)}

    @staticmethod
    def _anthropic_assemble(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        texts = [b.get('text') or '' for b in blocks if b.get('type') == 'text']
        message: Dict[str, Any] = {'role': 'assistant', 'content': ''.join(texts) or None}
        tool_calls = []
        for index, block in enumerate(blocks):
            if block.get('type') != 'tool_use':
                continue
            tool_calls.append({
                'id': block.get('id') or f'call_{index}',
                'type': 'function',
                'function': {
                    'name': block.get('name') or '',
                    'arguments': block.get('input_json') or json.dumps(block.get('input') or {}),
                },
            })
        if tool_calls:
            message['tool_calls'] = tool_calls
        return message

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
