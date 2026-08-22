"""AI 智能工作台的对话编排服务。

职责：
- 组织「系统提示词 + 会话历史 + 用户输入」并驱动大模型的多轮工具调用循环
- 把流式事件（token / tool_call / tool_result / done / error）以生成器形式交给 API 层
- 会话与消息持久化到 SQLite（AiChatSession / AiChatMessage）

实现说明：工具执行（如 inline 模式下同步下载数据）可能长时间阻塞，
整个智能体循环运行在后台线程中，通过队列把事件交给 SSE 生成器；
生成器在等待事件时定期产出心跳事件，避免代理层因空闲断开连接。
"""

import json
import logging
import queue
import threading
import time
from typing import Any, Dict, Iterator, List, Optional

from flask import current_app

from app.extensions import db
from app.models.ai_chat import AiChatMessage, AiChatSession
from app.services.ai.llm_client import LLMClient, LLMClientError
from app.services.ai.prompts import build_system_prompt
from app.services.ai.tools import execute_tool, get_tool_specs
from app.utils.time_utils import now_local

logger = logging.getLogger(__name__)

# 历史回放：最多携带的 user/assistant 消息条数与单条长度
HISTORY_MESSAGE_LIMIT = 16
HISTORY_MESSAGE_MAX_CHARS = 4000
# 持久化的工具结果上限
PERSIST_RESULT_MAX_CHARS = 20000
# 事件队列空闲多久后发一次心跳
HEARTBEAT_INTERVAL_SECONDS = 15.0


class AssistantError(Exception):
    """对话服务业务性错误（如未配置大模型）。"""


class AssistantService:
    def __init__(self, client: Optional[LLMClient] = None):
        self.config: Dict[str, Any] = dict(current_app.config.get('AI_ASSISTANT_CONFIG') or {})
        self.client = client or LLMClient(self.config)
        self.max_iterations = max(1, int(self.config.get('max_tool_iterations') or 10))

    # ------------------------------------------------------------------
    # 状态与会话管理（供 API 层调用）

    def status(self) -> Dict[str, Any]:
        from app.services.ai.prompts import build_status_hint
        from app.services.ai.tools import list_tool_summaries

        client_status = self.client.status_summary()
        status: Dict[str, Any] = {
            'llm': client_status,
            'tushare_token_configured': False,
            'tools': list_tool_summaries(allow_actions=True),
            'config_hint': None,
        }
        if not client_status['configured']:
            status['config_hint'] = build_status_hint(self.config)

        import os

        token = (os.getenv('TUSHARE_TOKEN') or '').strip()
        status['tushare_token_configured'] = token not in ('', 'your_tushare_token')

        try:
            from app.services.wide_table_status import get_wide_table_status

            data_dir = current_app.config.get('DATA_DIR', 'data')
            if data_dir and not str(data_dir).startswith('/'):
                data_dir = str(current_app.root_path) + '/../' + str(data_dir)
            wide = get_wide_table_status(data_dir)
            status['wide_table'] = {
                'exists': wide['exists'],
                'wide_table_date': wide['wide_table_date'],
                'should_update': wide['should_update'],
                'past_cutoff': wide['past_cutoff'],
            }
        except Exception as exc:
            logger.debug('读取宽表状态失败: %s', exc)
        return status

    def create_session(self, title: Optional[str] = None) -> AiChatSession:
        self._ensure_tables()
        session = AiChatSession(title=(title or '新对话').strip()[:128] or '新对话')
        db.session.add(session)
        db.session.commit()
        return session

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_tables()
        sessions = (
            AiChatSession.query.order_by(AiChatSession.updated_at.desc(), AiChatSession.id.desc())
            .limit(min(max(limit, 1), 200))
            .all()
        )
        return [session.to_dict() for session in sessions]

    def get_messages(self, session_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        self._ensure_tables()
        if AiChatSession.query.get(session_id) is None:
            raise AssistantError(f'会话不存在: {session_id}')
        messages = (
            AiChatMessage.query.filter_by(session_id=session_id)
            .order_by(AiChatMessage.id.desc())
            .limit(min(max(limit, 1), 500))
            .all()
        )
        return [message.to_dict() for message in reversed(messages)]

    def delete_session(self, session_id: int) -> bool:
        self._ensure_tables()
        session = AiChatSession.query.get(session_id)
        if session is None:
            return False
        AiChatMessage.query.filter_by(session_id=session_id).delete()
        db.session.delete(session)
        db.session.commit()
        return True

    # ------------------------------------------------------------------
    # 对话主流程

    def stream_chat(
        self,
        session_id: Optional[int],
        user_message: str,
        allow_actions: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        """返回事件生成器（见模块 docstring 的事件类型说明）。"""
        if not self.client.configured:
            raise AssistantError(
                '大模型接口未配置：请在 .env 中设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启服务'
            )
        user_message = (user_message or '').strip()
        if not user_message:
            raise AssistantError('消息内容不能为空')
        if len(user_message) > 8000:
            user_message = user_message[:8000]

        app = current_app._get_current_object()
        events: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()

        def emit(event: Dict[str, Any]):
            events.put(event)

        def worker():
            with app.app_context():
                try:
                    self._run_conversation(session_id, user_message, allow_actions, emit)
                except AssistantError as exc:
                    emit({'type': 'error', 'message': str(exc)})
                except LLMClientError as exc:
                    emit({'type': 'error', 'message': str(exc)})
                except Exception as exc:  # 兜底：任何异常都以错误事件结束会话
                    logger.exception('AI 会话执行异常')
                    emit({'type': 'error', 'message': f'会话内部错误: {exc}'})
                finally:
                    events.put(None)

        threading.Thread(target=worker, name='ai-assistant-loop', daemon=True).start()

        while True:
            try:
                event = events.get(timeout=HEARTBEAT_INTERVAL_SECONDS)
            except queue.Empty:
                yield {'type': 'heartbeat'}
                continue
            if event is None:
                break
            yield event

    # ------------------------------------------------------------------
    # 智能体循环（工作线程内执行）

    def _run_conversation(self, session_id, user_message, allow_actions, emit):
        self._ensure_tables()

        session = AiChatSession.query.get(session_id) if session_id else None
        created = False
        if session is None:
            session = AiChatSession(title=user_message[:30])
            db.session.add(session)
            db.session.commit()
            created = True
        emit(
            {
                'type': 'session',
                'session_id': session.id,
                'title': session.title,
                'created': created,
            }
        )

        db.session.add(AiChatMessage(session_id=session.id, role='user', content=user_message))
        session.updated_at = now_local()
        db.session.commit()

        messages: List[Dict[str, Any]] = [
            {'role': 'system', 'content': build_system_prompt(allow_actions, self.client.model)}
        ]
        messages.extend(self._load_history(session.id, exclude_recent=1))
        messages.append({'role': 'user', 'content': user_message})

        tools = get_tool_specs(allow_actions)
        assistant_reply = ''

        for _iteration in range(self.max_iterations):
            assembled: Optional[Dict[str, Any]] = None
            for event in self.client.chat(messages, tools=tools):
                if event['type'] == 'delta' and event.get('content'):
                    emit({'type': 'token', 'content': event['content']})
                elif event['type'] == 'message':
                    assembled = event['message']
                elif event['type'] == 'error':
                    raise LLMClientError(event.get('message') or '大模型调用失败')

            if assembled is None:
                raise LLMClientError('大模型未返回有效响应')

            messages.append(assembled)
            assistant_reply = assembled.get('content') or assistant_reply

            tool_calls = assembled.get('tool_calls') or []
            if not tool_calls:
                break

            for tool_call in tool_calls:
                function = tool_call.get('function') or {}
                name = function.get('name') or ''
                try:
                    arguments = json.loads(function.get('arguments') or '{}')
                    if not isinstance(arguments, dict):
                        arguments = {}
                except ValueError:
                    arguments = {}

                emit(
                    {
                        'type': 'tool_call',
                        'call_id': tool_call.get('id') or '',
                        'name': name,
                        'arguments': arguments,
                    }
                )

                started = time.time()
                outcome = execute_tool(name, arguments, allow_actions=allow_actions)
                duration_ms = int((time.time() - started) * 1000)

                self._save_tool_message(
                    session.id, name, arguments, outcome, duration_ms
                )
                emit(
                    {
                        'type': 'tool_result',
                        'call_id': tool_call.get('id') or '',
                        'name': name,
                        'ok': outcome['ok'],
                        'duration_ms': duration_ms,
                        'result': _frontend_payload(outcome),
                    }
                )
                messages.append(
                    {
                        'role': 'tool',
                        'tool_call_id': tool_call.get('id') or 'call',
                        'content': outcome.get('result_for_llm') or json.dumps(
                            {'error': outcome.get('error')}, ensure_ascii=False
                        ),
                    }
                )
            # 继续下一轮，让模型基于工具结果继续回答
        else:
            emit(
                {
                    'type': 'error',
                    'message': f'已达到单轮对话最大工具调用轮数（{self.max_iterations}），请缩小问题范围后继续',
                }
            )
            if assistant_reply:
                db.session.add(
                    AiChatMessage(session_id=session.id, role='assistant', content=assistant_reply)
                )
                db.session.commit()
            return

        db.session.add(AiChatMessage(session_id=session.id, role='assistant', content=assistant_reply))
        session.updated_at = now_local()
        db.session.commit()
        emit({'type': 'done', 'session_id': session.id})

    # ------------------------------------------------------------------
    # 内部辅助

    def _load_history(self, session_id: int, exclude_recent: int = 0) -> List[Dict[str, str]]:
        """回放最近的历史（仅 user/assistant 文本，工具记录不回放）。"""
        query = (
            AiChatMessage.query.filter(
                AiChatMessage.session_id == session_id,
                AiChatMessage.role.in_(['user', 'assistant']),
                AiChatMessage.content.isnot(None),
            )
            .order_by(AiChatMessage.id.desc())
        )
        rows = query.limit(HISTORY_MESSAGE_LIMIT + exclude_recent).all()
        rows = list(reversed(rows))
        if exclude_recent:
            rows = rows[:-exclude_recent]
        history = []
        for row in rows:
            content = (row.content or '').strip()
            if content:
                history.append({'role': row.role, 'content': content[:HISTORY_MESSAGE_MAX_CHARS]})
        return history

    def _save_tool_message(self, session_id, name, arguments, outcome, duration_ms):
        payload = outcome.get('result') if outcome['ok'] else {'error': outcome.get('error')}
        db.session.add(
            AiChatMessage(
                session_id=session_id,
                role='tool',
                content=None,
                tool_name=name,
                tool_args=arguments,
                tool_ok=outcome['ok'],
                tool_result=_persist_payload(payload),
                duration_ms=duration_ms,
            )
        )
        db.session.commit()

    _tables_ready = False
    _tables_lock = threading.Lock()

    @classmethod
    def _ensure_tables(cls):
        """首次使用时补建会话表（幂等，已有表不受影响）。"""
        if cls._tables_ready:
            return
        with cls._tables_lock:
            if cls._tables_ready:
                return
            db.create_all()
            cls._tables_ready = True


def _persist_payload(payload: Any) -> Any:
    """工具结果转为可持久化的 JSON（超长时截断保存预览）。"""
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {'_unserializable': str(payload)[:PERSIST_RESULT_MAX_CHARS]}
    if len(text) <= PERSIST_RESULT_MAX_CHARS:
        try:
            return json.loads(text)
        except ValueError:
            return {'_raw': text}
    return {'_truncated': True, 'preview': text[:PERSIST_RESULT_MAX_CHARS]}


def _frontend_payload(outcome: Dict[str, Any]) -> Any:
    """前端 tool_result 事件携带的结果（略小于持久化上限）。"""
    payload = outcome.get('result') if outcome['ok'] else {'error': outcome.get('error')}
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {'_unserializable': str(payload)[:8000]}
    if len(text) <= 8000:
        return payload
    return {'_truncated': True, 'preview': text[:8000]}
