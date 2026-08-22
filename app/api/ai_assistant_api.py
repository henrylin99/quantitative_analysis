"""AI 智能工作台 API。

- GET  /api/ai-assistant/status                 配置与能力状态
- GET|POST /api/ai-assistant/sessions           会话列表 / 新建会话
- DELETE /api/ai-assistant/sessions/<id>        删除会话
- GET  /api/ai-assistant/sessions/<id>/messages 会话消息历史
- POST /api/ai-assistant/chat                   对话（SSE 流式响应）
"""

import json
import logging

from flask import Blueprint, Response, jsonify, request, stream_with_context

from app.services.ai.assistant_service import AssistantError, AssistantService

logger = logging.getLogger(__name__)

ai_assistant_bp = Blueprint('ai_assistant', __name__, url_prefix='/api/ai-assistant')


@ai_assistant_bp.route('/status', methods=['GET'])
def status():
    try:
        service = AssistantService()
        return jsonify({'success': True, 'data': service.status()})
    except Exception as exc:
        logger.exception('获取 AI 工作台状态失败')
        return jsonify({'success': False, 'error': str(exc)}), 500


@ai_assistant_bp.route('/sessions', methods=['GET'])
def list_sessions():
    try:
        limit = int(request.args.get('limit', 50))
        return jsonify({'success': True, 'sessions': AssistantService().list_sessions(limit)})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@ai_assistant_bp.route('/sessions', methods=['POST'])
def create_session():
    payload = request.get_json(silent=True) or {}
    try:
        session = AssistantService().create_session(payload.get('title'))
        return jsonify({'success': True, 'session': session.to_dict()}), 201
    except Exception as exc:
        logger.exception('创建会话失败')
        return jsonify({'success': False, 'error': str(exc)}), 500


@ai_assistant_bp.route('/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    try:
        deleted = AssistantService().delete_session(session_id)
        if not deleted:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@ai_assistant_bp.route('/sessions/<int:session_id>/messages', methods=['GET'])
def session_messages(session_id):
    try:
        limit = int(request.args.get('limit', 200))
        return jsonify({'success': True, 'messages': AssistantService().get_messages(session_id, limit)})
    except AssistantError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@ai_assistant_bp.route('/chat', methods=['POST'])
def chat():
    """流式对话。响应为 text/event-stream，每条 data 为 JSON 事件：
    session / token / tool_call / tool_result / heartbeat / done / error
    """
    payload = request.get_json(silent=True) or {}
    message = (payload.get('message') or '').strip()
    if not message:
        return jsonify({'success': False, 'error': '消息内容不能为空'}), 400

    session_id = payload.get('session_id')
    allow_actions = bool(payload.get('allow_actions', True))

    service = AssistantService()
    if not service.client.configured:
        return (
            jsonify(
                {
                    'success': False,
                    'error': '大模型接口未配置：请在 .env 中设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启服务',
                }
            ),
            400,
        )

    try:
        # 提前校验 session_id 存在性，避免进入流后才发现参数错误
        if session_id is not None:
            from app.models.ai_chat import AiChatSession

            if AiChatSession.query.get(session_id) is None:
                return jsonify({'success': False, 'error': f'会话不存在: {session_id}'}), 404
    except AssistantError:
        return jsonify({'success': False, 'error': '会话服务不可用'}), 500

    def sse_stream():
        try:
            for event in service.stream_chat(session_id, message, allow_actions=allow_actions):
                yield f'data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n'
        except AssistantError as exc:
            yield f'data: {json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)}\n\n'
        except Exception as exc:  # pragma: no cover - 流中断兜底
            logger.exception('AI 对话流中断')
            yield f'data: {json.dumps({"type": "error", "message": f"对话流中断: {exc}"}, ensure_ascii=False)}\n\n'

    response = Response(
        stream_with_context(sse_stream()),
        mimetype='text/event-stream',
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response
