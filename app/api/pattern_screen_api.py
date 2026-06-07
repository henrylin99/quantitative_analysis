"""形态选股 API 端点。"""
from flask import Blueprint, request, jsonify
from loguru import logger

pattern_screen_api = Blueprint('pattern_screen_api', __name__, url_prefix='/api/pattern-screen')


@pattern_screen_api.route('/groups', methods=['GET'])
def get_groups():
    """返回形态分组元数据（含命中数）。"""
    try:
        from app.services.pattern_screen_service import get_pattern_screen_service
        svc = get_pattern_screen_service()
        groups = svc.get_groups()
        return jsonify({'code': 200, 'message': '成功', 'data': groups})
    except Exception as e:
        logger.error(f"获取形态分组失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@pattern_screen_api.route('/screen', methods=['POST'])
def screen():
    """执行形态筛选，返回结果表格。"""
    try:
        data = request.get_json() or {}
        patterns = data.get('patterns', [])
        sort_by = data.get('sort_by', 'pct_chg')
        order = data.get('order', 'desc')
        limit = data.get('limit', 50)
        offset = data.get('offset', 0)

        from app.services.pattern_screen_service import get_pattern_screen_service
        svc = get_pattern_screen_service()
        result = svc.screen(
            patterns=patterns,
            sort_by=sort_by,
            order=order,
            limit=limit,
            offset=offset,
        )
        return jsonify({'code': 200, 'message': '成功', 'data': result})
    except ValueError as e:
        logger.warning(f"形态筛选参数错误: {e}")
        return jsonify({'code': 400, 'message': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"形态筛选失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500
