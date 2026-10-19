"""港股行情 API 端点（数据为雅虎财经离线快照，非实时）。"""
from flask import Blueprint, jsonify, request
from loguru import logger

hk_stock_api = Blueprint('hk_stock_api', __name__, url_prefix='/api/hk-stock')


@hk_stock_api.route('/meta', methods=['GET'])
def get_meta():
    """股票池元信息：数量 + 数据日期。"""
    try:
        from app.services import hk_stock_service
        return jsonify({'code': 200, 'message': '成功', 'data': hk_stock_service.build_meta()})
    except Exception as e:
        logger.error(f"获取港股元信息失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@hk_stock_api.route('/stocks', methods=['GET'])
def get_stocks():
    """港股列表：关键字搜索 + 排序 + 分页。"""
    try:
        from app.services import hk_stock_service
        result = hk_stock_service.query_stocks(
            q=request.args.get('q'),
            sort_by=request.args.get('sort_by'),
            sort_asc=request.args.get('sort_asc', 'false').lower() == 'true',
            offset=max(0, request.args.get('offset', 0, type=int)),
            limit=min(500, max(1, request.args.get('limit', 50, type=int))),
        )
        return jsonify({'code': 200, 'message': '成功', 'data': result})
    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"获取港股列表失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@hk_stock_api.route('/stocks/<symbol>', methods=['GET'])
def get_stock(symbol: str):
    """单只港股快照（最新一行全字段）。"""
    try:
        from app.services import hk_stock_service
        return jsonify({'code': 200, 'message': '成功', 'data': hk_stock_service.query_stock_snapshot(symbol.upper())})
    except ValueError as e:
        return jsonify({'code': 404, 'message': str(e), 'data': None}), 404
    except Exception as e:
        logger.error(f"获取港股详情失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@hk_stock_api.route('/stocks/<symbol>/history', methods=['GET'])
def get_stock_history(symbol: str):
    """单只港股历史 K 线，range ∈ {3m, 6m, 1y, 2y}，默认 6m。"""
    try:
        from app.services import hk_stock_service
        range_key = request.args.get('range', '6m')
        return jsonify({'code': 200, 'message': '成功', 'data': hk_stock_service.query_stock_history(symbol.upper(), range_key)})
    except ValueError as e:
        return jsonify({'code': 404, 'message': str(e), 'data': None}), 404
    except Exception as e:
        logger.error(f"获取港股历史失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@hk_stock_api.route('/sync', methods=['POST'])
def start_hk_sync():
    """后台启动 build_snapshot.py 同步（雅虎财经离线快照刷新，约 3-8 分钟）。"""
    try:
        from app.services import market_sync_service
        state, started = market_sync_service.start_sync('hk')
        if not started:
            return jsonify({'code': 409, 'message': '同步已在进行中', 'data': state}), 409
        return jsonify({'code': 200, 'message': '同步任务已启动', 'data': state})
    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"启动hk同步失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@hk_stock_api.route('/sync', methods=['GET'])
def get_hk_sync_status():
    """同步状态 + 最新数据日期/数量。"""
    try:
        from app.services import market_sync_service
        return jsonify({'code': 200, 'message': '成功', 'data': market_sync_service.get_status('hk')})
    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"获取hk同步状态失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500
