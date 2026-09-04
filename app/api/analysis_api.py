from flask import request, jsonify
from app.api import api_bp
from app.services.stock_service import StockService
from loguru import logger
from datetime import datetime, timedelta

@api_bp.route('/analysis/screen', methods=['POST'])
def screen_stocks():
    """股票筛选"""
    try:
        data = request.get_json()
        logger.info(f"收到筛选请求: {data}")
        
        # 使用StockService进行筛选
        result = StockService.screen_stocks(data)
        
        return jsonify({
            'code': 200,
            'message': '筛选完成',
            'data': result
        })
    except Exception as e:
        logger.error(f"股票筛选API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/analysis/backtest', methods=['POST'])
def backtest_strategy():
    """策略回测"""
    try:
        data = request.get_json()
        logger.info(f"收到回测请求: {data}")
        
        # 验证必要参数
        required_fields = ['ts_code', 'strategy_type', 'start_date', 'end_date', 'initial_capital']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'code': 400,
                    'message': f'缺少必要参数: {field}',
                    'data': None
                }), 400
        
        # 获取历史数据
        ts_code = data['ts_code']
        start_date = data['start_date']
        end_date = data['end_date']
        
        # 获取更多历史数据用于计算技术指标
        extended_start = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=100)
        extended_start_str = extended_start.strftime('%Y-%m-%d')
        
        history_data = StockService.get_daily_history(
            ts_code, 
            start_date=extended_start_str, 
            end_date=end_date, 
            limit=500
        )
        
        if not history_data or len(history_data) < 30:
            return jsonify({
                'code': 400,
                'message': '历史数据不足，无法进行回测',
                'data': None
            }), 400
        
        # 获取技术因子数据
        factors_data = StockService.get_stock_factors(
            ts_code,
            start_date=extended_start_str,
            end_date=end_date,
            limit=500
        )
        
        # 执行回测
        backtest_engine = BacktestEngine(data)
        result = backtest_engine.run_backtest(history_data, factors_data)
        
        return jsonify({
            'code': 200,
            'message': '回测完成',
            'data': result
        })
        
    except Exception as e:
        logger.error(f"策略回测API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'回测失败: {str(e)}',
            'data': None
        }), 500


from app.services.single_stock_backtest import SingleStockBacktestEngine as BacktestEngine
