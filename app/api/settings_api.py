"""系统设置 API：tushare / 扶摇 / 大模型配置的读取与在线修改。

- GET  /api/settings        三类配置状态（脱敏回显；?probe=1 附 fuyao 真实探测）
- POST /api/settings        在线修改（写 .env + os.environ，不重启即生效）

写入受全局 API_AUTH_TOKEN 门禁保护（/api/* before_request，见 app/__init__.py）；
token 值不落日志。
"""

import logging

from flask import Blueprint, jsonify, request

from app.services import settings_service

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')


def _ok(data):
    return jsonify({'code': 200, 'message': '成功', 'data': data})


def _error(message: str, code: int = 400):
    return jsonify({'code': code, 'message': message, 'data': None}), code


@settings_bp.route('', methods=['GET'])
def get_settings():
    try:
        probe = request.args.get('probe') in ('1', 'true', 'yes')
        return _ok(settings_service.get_settings(probe_fuyao=probe))
    except Exception:
        logger.exception('读取系统配置状态失败')
        return _error('服务器内部错误，请查看服务日志', 500)


@settings_bp.route('', methods=['POST'])
def update_settings():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _error('请求体必须是 JSON 对象')
        if not payload:
            return _error('没有可更新的配置项')
        result = settings_service.update_settings(payload)
        return _ok(result)
    except ValueError as exc:
        return _error(str(exc))
    except Exception:
        logger.exception('更新系统配置失败')
        return _error('服务器内部错误，请查看服务日志', 500)


@settings_bp.route('/test-llm', methods=['POST'])
def test_llm():
    """真实调用一次大模型验证配置可用性。

    body 可选 {provider, base_url, model, api_key}——传了就用传入值测试
    （用户保存前先试），全空则测当前 .env 生效配置。api_key 不落日志。
    """
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _error('请求体必须是 JSON 对象')
        result = settings_service.test_llm(
            provider=str(payload.get('provider') or ''),
            base_url=str(payload.get('base_url') or ''),
            model=str(payload.get('model') or ''),
            api_key=str(payload.get('api_key') or ''),
        )
        return _ok(result)
    except Exception:
        logger.exception('大模型连通性测试失败')
        return _error('服务器内部错误，请查看服务日志', 500)
