"""
实时交易信号API接口
提供交易信号生成、融合、查询和管理功能
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import logging

from app.services.realtime_trading_signal_engine import RealtimeTradingSignalEngine
from app.models.trading_signal import TradingSignal

logger = logging.getLogger(__name__)

# 创建蓝图
realtime_signals_bp = Blueprint('realtime_signals', __name__)

# 初始化信号引擎
signal_engine = RealtimeTradingSignalEngine()


@realtime_signals_bp.route('/generate', methods=['POST'])
def generate_signals():
    """生成交易信号"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        period_type = data.get('period_type', '1min')
        strategies = data.get('strategies')  # 可选，None表示使用所有策略
        lookback_days = data.get('lookback_days', 5)
        
        if not ts_code:
            return jsonify({'success': False, 'message': '股票代码不能为空'})
        
        # 生成信号
        result = signal_engine.generate_signals(
            ts_code=ts_code,
            period_type=period_type,
            strategies=strategies,
            lookback_days=lookback_days
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"生成交易信号失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/fuse', methods=['POST'])
def fuse_signals():
    """信号融合"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        period_type = data.get('period_type', '1min')
        time_window_hours = data.get('time_window_hours', 1)
        
        if not ts_code:
            return jsonify({'success': False, 'message': '股票代码不能为空'})
        
        # 融合信号
        result = signal_engine.fuse_signals(
            ts_code=ts_code,
            period_type=period_type,
            time_window_hours=time_window_hours
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"信号融合失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/active', methods=['GET'])
def get_active_signals():
    """获取活跃信号"""
    try:
        ts_code = request.args.get('ts_code')
        strategy_name = request.args.get('strategy_name')
        limit = int(request.args.get('limit', 100))
        
        # 获取活跃信号
        signals = TradingSignal.get_active_signals(
            ts_code=ts_code,
            strategy_name=strategy_name,
            limit=limit
        )
        
        # 转换为字典格式
        result_data = [signal.to_dict() for signal in signals]
        
        return jsonify({
            'success': True,
            'data': result_data,
            'total': len(result_data),
            'ts_code': ts_code,
            'strategy_name': strategy_name
        })
        
    except Exception as e:
        logger.error(f"获取活跃信号失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/history', methods=['GET'])
def get_signal_history():
    """获取信号历史"""
    try:
        ts_code = request.args.get('ts_code')
        strategy_name = request.args.get('strategy_name')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        
        # 解析时间参数
        start_dt = None
        end_dt = None
        
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        # 如果没有指定时间范围，默认查询最近7天
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=7)
        
        # 获取信号历史
        signals = TradingSignal.get_signals_by_time_range(
            start_time=start_dt,
            end_time=end_dt,
            ts_code=ts_code,
            strategy_name=strategy_name
        )
        
        # 转换为字典格式
        result_data = [signal.to_dict() for signal in signals]
        
        return jsonify({
            'success': True,
            'data': result_data,
            'total': len(result_data),
            'ts_code': ts_code,
            'strategy_name': strategy_name,
            'start_time': start_dt.isoformat() if start_dt else None,
            'end_time': end_dt.isoformat() if end_dt else None
        })
        
    except Exception as e:
        logger.error(f"获取信号历史失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/performance', methods=['GET'])
def get_signal_performance():
    """获取信号表现"""
    try:
        strategy_name = request.args.get('strategy_name')
        days = int(request.args.get('days', 30))
        
        # 获取信号表现统计
        performance = TradingSignal.get_signal_performance(
            strategy_name=strategy_name,
            days=days
        )
        
        return jsonify({
            'success': True,
            'data': performance,
            'strategy_name': strategy_name,
            'days': days
        })
        
    except Exception as e:
        logger.error(f"获取信号表现失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/strategies', methods=['GET'])
def get_supported_strategies():
    """获取支持的策略列表"""
    try:
        strategies = signal_engine.get_supported_strategies()
        
        return jsonify({
            'success': True,
            'data': strategies,
            'total': len(strategies)
        })
        
    except Exception as e:
        logger.error(f"获取支持的策略列表失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/backtest', methods=['POST'])
def backtest_strategy():
    """策略回测"""
    try:
        data = request.get_json()
        strategy_name = data.get('strategy_name')
        ts_code = data.get('ts_code')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        period_type = data.get('period_type', '1min')
        
        if not all([strategy_name, ts_code, start_date, end_date]):
            return jsonify({
                'success': False, 
                'message': '策略名称、股票代码、开始日期和结束日期不能为空'
            })
        
        # 执行回测
        result = signal_engine.backtest_strategy(
            strategy_name=strategy_name,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            period_type=period_type
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"策略回测失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/batch-generate', methods=['POST'])
def batch_generate_signals():
    """批量生成信号"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        period_type = data.get('period_type', '1min')
        strategies = data.get('strategies')
        lookback_days = data.get('lookback_days', 5)
        
        if not stock_codes:
            return jsonify({'success': False, 'message': '股票代码列表不能为空'})
        
        results = {}
        success_count = 0
        error_count = 0
        total_signals = 0
        
        for ts_code in stock_codes:
            try:
                result = signal_engine.generate_signals(
                    ts_code=ts_code,
                    period_type=period_type,
                    strategies=strategies,
                    lookback_days=lookback_days
                )
                
                results[ts_code] = result
                if result.get('success'):
                    success_count += 1
                    total_signals += result.get('data', {}).get('signals_generated', 0)
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"生成 {ts_code} 信号失败: {str(e)}")
                results[ts_code] = {'success': False, 'message': str(e)}
                error_count += 1
        
        return jsonify({
            'success': True,
            'data': results,
            'summary': {
                'total_stocks': len(stock_codes),
                'success': success_count,
                'error': error_count,
                'total_signals_generated': total_signals
            }
        })
        
    except Exception as e:
        logger.error(f"批量生成信号失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/update-status', methods=['POST'])
def update_signal_status():
    """更新信号状态"""
    try:
        data = request.get_json()
        signal_id = data.get('signal_id')
        status = data.get('status')
        executed_price = data.get('executed_price')
        profit_loss = data.get('profit_loss')
        
        if not signal_id or not status:
            return jsonify({'success': False, 'message': '信号ID和状态不能为空'})
        
        # 更新信号状态
        success, message = TradingSignal.update_signal_status(
            signal_id=signal_id,
            status=status,
            executed_price=executed_price,
            profit_loss=profit_loss
        )
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"更新信号状态失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/expire-old', methods=['POST'])
def expire_old_signals():
    """过期旧信号"""
    try:
        data = request.get_json()
        hours = data.get('hours', 24)
        
        # 过期旧信号
        success, message = TradingSignal.expire_old_signals(hours=hours)
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"过期旧信号失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/stats', methods=['GET'])
def get_signal_stats():
    """获取信号统计信息"""
    try:
        stats = TradingSignal.get_signal_stats()
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        logger.error(f"获取信号统计信息失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/multi-stock-fusion', methods=['POST'])
def multi_stock_fusion():
    """多股票信号融合"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        period_type = data.get('period_type', '1min')
        time_window_hours = data.get('time_window_hours', 1)
        
        if not stock_codes:
            return jsonify({'success': False, 'message': '股票代码列表不能为空'})
        
        fusion_results = {}
        
        for ts_code in stock_codes:
            try:
                result = signal_engine.fuse_signals(
                    ts_code=ts_code,
                    period_type=period_type,
                    time_window_hours=time_window_hours
                )
                fusion_results[ts_code] = result
                
            except Exception as e:
                logger.error(f"融合 {ts_code} 信号失败: {str(e)}")
                fusion_results[ts_code] = {'success': False, 'message': str(e)}
        
        return jsonify({
            'success': True,
            'data': fusion_results,
            'stock_codes': stock_codes,
            'period_type': period_type,
            'time_window_hours': time_window_hours
        })
        
    except Exception as e:
        logger.error(f"多股票信号融合失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_signals_bp.route('/signal-strength-distribution', methods=['GET'])
def get_signal_strength_distribution():
    """获取信号强度分布"""
    try:
        ts_code = request.args.get('ts_code')
        strategy_name = request.args.get('strategy_name')
        days = int(request.args.get('days', 30))
        
        # 获取最近N天的信号
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        signals = TradingSignal.get_signals_by_time_range(
            start_time=start_time,
            end_time=end_time,
            ts_code=ts_code,
            strategy_name=strategy_name
        )
        
        # 统计信号强度分布
        strength_ranges = {
            'strong_buy': 0,    # 0.7 - 1.0
            'buy': 0,           # 0.3 - 0.7
            'weak_buy': 0,      # 0.0 - 0.3
            'weak_sell': 0,     # -0.3 - 0.0
            'sell': 0,          # -0.7 - -0.3
            'strong_sell': 0    # -1.0 - -0.7
        }
        
        for signal in signals:
            strength = signal.signal_strength
            if strength >= 0.7:
                strength_ranges['strong_buy'] += 1
            elif strength >= 0.3:
                strength_ranges['buy'] += 1
            elif strength >= 0.0:
                strength_ranges['weak_buy'] += 1
            elif strength >= -0.3:
                strength_ranges['weak_sell'] += 1
            elif strength >= -0.7:
                strength_ranges['sell'] += 1
            else:
                strength_ranges['strong_sell'] += 1
        
        return jsonify({
            'success': True,
            'data': {
                'distribution': strength_ranges,
                'total_signals': len(signals),
                'ts_code': ts_code,
                'strategy_name': strategy_name,
                'days': days
            }
        })
        
    except Exception as e:
        logger.error(f"获取信号强度分布失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}) 