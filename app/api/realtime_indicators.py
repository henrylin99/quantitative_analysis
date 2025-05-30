"""
实时技术指标API接口
提供技术指标计算、查询和管理功能
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import logging
import json
import numpy as np
import pandas as pd
import math

from app.services.realtime_indicator_engine import RealtimeIndicatorEngine
from app.models.realtime_indicator import RealtimeIndicator
from app.models.stock_minute_data import StockMinuteData

logger = logging.getLogger(__name__)

# 创建蓝图
realtime_indicators_bp = Blueprint('realtime_indicators', __name__)

# 初始化指标引擎
indicator_engine = RealtimeIndicatorEngine()


@realtime_indicators_bp.route('/calculate', methods=['POST'])
def calculate_indicators():
    """计算技术指标"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        period_type = data.get('period_type', '1min')
        indicators = data.get('indicators')  # 可选，None表示计算所有指标
        lookback_days = data.get('lookback_days', 30)
        
        if not ts_code:
            return jsonify({'success': False, 'message': '股票代码不能为空'})
        
        # 计算指标
        result = indicator_engine.calculate_indicators(
            ts_code=ts_code,
            period_type=period_type,
            indicators=indicators,
            lookback_days=lookback_days
        )
        
        # 第一步：使用自定义JSON编码器
        class NaNEncoder(json.JSONEncoder):
            def encode(self, obj):
                if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                    return 'null'
                return super().encode(obj)
            
            def iterencode(self, obj, _one_shot=False):
                """Encode the given object and yield each string representation as available."""
                for chunk in super().iterencode(obj, _one_shot):
                    # 替换任何剩余的NaN值
                    chunk = chunk.replace('NaN', 'null')
                    chunk = chunk.replace('Infinity', 'null')
                    chunk = chunk.replace('-Infinity', 'null')
                    yield chunk
        
        # 第二步：强力清理NaN值
        def clean_nan_values(obj):
            """递归清理所有NaN值"""
            import math
            
            if obj is None:
                return None
            elif isinstance(obj, dict):
                return {k: clean_nan_values(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan_values(v) for v in obj]
            elif isinstance(obj, tuple):
                return tuple(clean_nan_values(v) for v in obj)
            elif isinstance(obj, pd.Series):
                # 处理pandas Series
                return [clean_nan_values(item) for item in obj.tolist()]
            elif isinstance(obj, np.ndarray):
                # 处理numpy数组
                return [clean_nan_values(item) for item in obj.tolist()]
            elif isinstance(obj, (np.integer, np.floating)):
                # 处理numpy数值类型
                if np.isnan(obj) or np.isinf(obj):
                    return None
                return obj.item()
            elif isinstance(obj, (int, float)):
                # 处理Python数值类型
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            elif hasattr(obj, 'item'):  # 其他numpy标量
                try:
                    val = obj.item()
                    return clean_nan_values(val)
                except:
                    return None
            else:
                return obj
        
        # 清理结果
        cleaned_result = clean_nan_values(result)
        
        # 第三步：使用自定义编码器转换为JSON
        json_str = json.dumps(cleaned_result, cls=NaNEncoder, allow_nan=False)
        
        # 第四步：字符串级别的最终清理
        json_str = json_str.replace('NaN', 'null')
        json_str = json_str.replace('Infinity', 'null')
        json_str = json_str.replace('-Infinity', 'null')
        
        # 重新解析为Python对象
        final_result = json.loads(json_str)
        
        return jsonify(final_result)
        
    except Exception as e:
        logger.error(f"计算技术指标失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/multi-period', methods=['POST'])
def calculate_multi_period():
    """计算多周期指标"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        indicators = data.get('indicators')
        periods = data.get('periods')
        
        if not ts_code:
            return jsonify({'success': False, 'message': '股票代码不能为空'})
        
        # 计算多周期指标
        result = indicator_engine.calculate_multi_period_indicators(
            ts_code=ts_code,
            indicators=indicators,
            periods=periods
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"计算多周期指标失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/latest', methods=['GET'])
def get_latest_indicators():
    """获取最新指标数据"""
    try:
        ts_code = request.args.get('ts_code')
        period_type = request.args.get('period_type', '1min')
        indicator_names = request.args.getlist('indicators')
        limit = int(request.args.get('limit', 100))
        
        if not ts_code:
            return jsonify({'success': False, 'message': '股票代码不能为空'})
        
        # 获取最新指标数据
        indicators = RealtimeIndicator.get_latest_indicators(
            ts_code=ts_code,
            period_type=period_type,
            indicator_names=indicator_names if indicator_names else None,
            limit=limit
        )
        
        # 转换为字典格式
        result_data = [indicator.to_dict() for indicator in indicators]
        
        return jsonify({
            'success': True,
            'data': result_data,
            'total': len(result_data),
            'ts_code': ts_code,
            'period_type': period_type
        })
        
    except Exception as e:
        logger.error(f"获取最新指标数据失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/history', methods=['GET'])
def get_indicator_history():
    """获取指标历史数据"""
    try:
        ts_code = request.args.get('ts_code')
        period_type = request.args.get('period_type', '1min')
        indicator_name = request.args.get('indicator_name')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        
        if not ts_code or not indicator_name:
            return jsonify({'success': False, 'message': '股票代码和指标名称不能为空'})
        
        # 解析时间参数
        start_dt = None
        end_dt = None
        
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        # 获取指标历史数据
        indicators = RealtimeIndicator.get_indicator_history(
            ts_code=ts_code,
            period_type=period_type,
            indicator_name=indicator_name,
            start_time=start_dt,
            end_time=end_dt
        )
        
        # 转换为字典格式
        result_data = [indicator.to_dict() for indicator in indicators]
        
        return jsonify({
            'success': True,
            'data': result_data,
            'total': len(result_data),
            'ts_code': ts_code,
            'period_type': period_type,
            'indicator_name': indicator_name
        })
        
    except Exception as e:
        logger.error(f"获取指标历史数据失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/supported', methods=['GET'])
def get_supported_indicators():
    """获取支持的指标列表"""
    try:
        indicators = indicator_engine.get_supported_indicators()
        
        return jsonify({
            'success': True,
            'data': indicators,
            'total': len(indicators)
        })
        
    except Exception as e:
        logger.error(f"获取支持的指标列表失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/stats', methods=['GET'])
def get_indicator_stats():
    """获取指标统计信息"""
    try:
        stats = RealtimeIndicator.get_indicator_stats()
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        logger.error(f"获取指标统计信息失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/batch-calculate', methods=['POST'])
def batch_calculate_indicators():
    """批量计算指标"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        period_type = data.get('period_type', '1min')
        indicators = data.get('indicators')
        lookback_days = data.get('lookback_days', 7)
        
        if not stock_codes:
            return jsonify({'success': False, 'message': '股票代码列表不能为空'})
        
        results = {}
        success_count = 0
        error_count = 0
        
        for ts_code in stock_codes:
            try:
                result = indicator_engine.calculate_indicators(
                    ts_code=ts_code,
                    period_type=period_type,
                    indicators=indicators,
                    lookback_days=lookback_days
                )
                
                results[ts_code] = result
                if result.get('success'):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"计算 {ts_code} 指标失败: {str(e)}")
                results[ts_code] = {'success': False, 'message': str(e)}
                error_count += 1
        
        return jsonify({
            'success': True,
            'data': results,
            'summary': {
                'total': len(stock_codes),
                'success': success_count,
                'error': error_count
            }
        })
        
    except Exception as e:
        logger.error(f"批量计算指标失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/compare', methods=['POST'])
def compare_indicators():
    """比较多个股票的指标"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        period_type = data.get('period_type', '1min')
        indicator_name = data.get('indicator_name')
        limit = data.get('limit', 50)
        
        if not stock_codes or not indicator_name:
            return jsonify({'success': False, 'message': '股票代码列表和指标名称不能为空'})
        
        results = {}
        
        for ts_code in stock_codes:
            try:
                indicators = RealtimeIndicator.get_latest_indicators(
                    ts_code=ts_code,
                    period_type=period_type,
                    indicator_names=[indicator_name],
                    limit=limit
                )
                
                results[ts_code] = [indicator.to_dict() for indicator in indicators]
                
            except Exception as e:
                logger.error(f"获取 {ts_code} 指标数据失败: {str(e)}")
                results[ts_code] = []
        
        return jsonify({
            'success': True,
            'data': results,
            'indicator_name': indicator_name,
            'period_type': period_type,
            'stock_codes': stock_codes
        })
        
    except Exception as e:
        logger.error(f"比较指标失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_indicators_bp.route('/cleanup', methods=['POST'])
def cleanup_old_data():
    """清理旧的指标数据"""
    try:
        data = request.get_json()
        days_to_keep = data.get('days_to_keep', 30)
        
        success, message = RealtimeIndicator.cleanup_old_data(days_to_keep)
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"清理旧数据失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}) 