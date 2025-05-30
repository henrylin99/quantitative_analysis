from flask import request, jsonify
from app.api import api_bp
from app.services.stock_service import StockService
from loguru import logger

@api_bp.route('/stocks', methods=['GET'])
def get_stocks():
    """获取股票列表"""
    try:
        # 获取查询参数
        industry = request.args.get('industry')
        area = request.args.get('area')
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
        
        # 调用服务
        result = StockService.get_stock_list(
            industry=industry,
            area=area,
            page=page,
            page_size=page_size
        )
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取股票列表API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/stocks/<ts_code>', methods=['GET'])
def get_stock_detail(ts_code):
    """获取股票基本信息"""
    try:
        result = StockService.get_stock_info(ts_code)
        
        if result is None:
            return jsonify({
                'code': 404,
                'message': '股票不存在',
                'data': None
            }), 404
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取股票详情API错误: {ts_code}, {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/stocks/<ts_code>/history', methods=['GET'])
def get_stock_history(ts_code):
    """获取股票历史数据"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 60))
        
        result = StockService.get_daily_history(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取股票历史数据API错误: {ts_code}, {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/stocks/<ts_code>/factors', methods=['GET'])
def get_stock_factors(ts_code):
    """获取股票技术因子数据"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 60))
        
        result = StockService.get_stock_factors(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取股票技术因子API错误: {ts_code}, {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/stocks/<ts_code>/moneyflow', methods=['GET'])
def get_stock_moneyflow(ts_code):
    """获取股票资金流向数据"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 30))
        
        result = StockService.get_moneyflow(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取股票资金流向API错误: {ts_code}, {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/stocks/<ts_code>/cyq', methods=['GET'])
def get_stock_cyq(ts_code):
    """获取股票筹码分布数据"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 30))
        
        result = StockService.get_cyq_perf(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取股票筹码分布API错误: {ts_code}, {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/industries', methods=['GET'])
def get_industries():
    """获取行业列表"""
    try:
        result = StockService.get_industry_list()
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取行业列表API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/areas', methods=['GET'])
def get_areas():
    """获取地域列表"""
    try:
        result = StockService.get_area_list()
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': result
        })
    except Exception as e:
        logger.error(f"获取地域列表API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500 