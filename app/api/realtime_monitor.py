"""
实时监控API接口
提供实时行情监控、热点板块监控、异动股票监控和市场情绪监控功能
"""

from flask import Blueprint, request, jsonify
import logging

from app.services.realtime_monitor_service import RealtimeMonitorService

logger = logging.getLogger(__name__)

# 创建蓝图
realtime_monitor_bp = Blueprint('realtime_monitor', __name__)

# 初始化监控服务
monitor_service = RealtimeMonitorService()


@realtime_monitor_bp.route('/overview', methods=['GET'])
def get_monitor_overview():
    """获取监控概览"""
    try:
        result = monitor_service.get_monitor_overview()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取监控概览失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/quotes', methods=['GET'])
def get_realtime_quotes():
    """获取实时行情"""
    try:
        # 获取请求参数
        stock_codes_param = request.args.get('stock_codes')
        period_type = request.args.get('period_type', '1min')
        limit = int(request.args.get('limit', 50))
        
        # 解析股票代码列表
        stock_codes = None
        if stock_codes_param:
            stock_codes = [code.strip() for code in stock_codes_param.split(',') if code.strip()]
        
        result = monitor_service.get_realtime_quotes(
            stock_codes=stock_codes,
            period_type=period_type,
            limit=limit
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取实时行情失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/sectors', methods=['GET'])
def get_sector_performance():
    """获取板块表现"""
    try:
        period_hours = int(request.args.get('period_hours', 1))
        
        result = monitor_service.get_sector_performance(period_hours=period_hours)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取板块表现失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/anomalies', methods=['GET'])
def detect_anomalies():
    """检测异动股票"""
    try:
        change_threshold = float(request.args.get('change_threshold', 5.0))
        volume_threshold = float(request.args.get('volume_threshold', 3.0))
        period_hours = int(request.args.get('period_hours', 1))
        
        result = monitor_service.detect_anomalies(
            change_threshold=change_threshold,
            volume_threshold=volume_threshold,
            period_hours=period_hours
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"检测异动股票失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/sentiment', methods=['GET'])
def get_market_sentiment():
    """获取市场情绪"""
    try:
        period_hours = int(request.args.get('period_hours', 1))
        
        result = monitor_service.get_market_sentiment(period_hours=period_hours)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取市场情绪失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/watchlist', methods=['POST'])
def add_to_watchlist():
    """添加到监控列表"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        
        if not stock_codes:
            return jsonify({'success': False, 'message': '股票代码列表不能为空'})
        
        # 获取这些股票的实时行情
        result = monitor_service.get_realtime_quotes(
            stock_codes=stock_codes,
            period_type='1min',
            limit=len(stock_codes)
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'data': result.get('data'),
                'message': f'成功添加 {len(stock_codes)} 只股票到监控列表'
            })
        else:
            return jsonify(result)
        
    except Exception as e:
        logger.error(f"添加监控列表失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/alerts', methods=['GET'])
def get_price_alerts():
    """获取价格预警"""
    try:
        # 获取异动股票作为预警
        change_threshold = float(request.args.get('change_threshold', 3.0))
        volume_threshold = float(request.args.get('volume_threshold', 2.0))
        
        anomalies_result = monitor_service.detect_anomalies(
            change_threshold=change_threshold,
            volume_threshold=volume_threshold,
            period_hours=1
        )
        
        if not anomalies_result.get('success'):
            return jsonify(anomalies_result)
        
        # 转换为预警格式
        alerts = []
        for anomaly in anomalies_result.get('data', {}).get('anomalies', []):
            alert_type = 'price_up' if anomaly['change_pct'] > 0 else 'price_down'
            if 'volume' in anomaly.get('anomaly_types', []):
                alert_type += '_volume'
            
            alerts.append({
                'ts_code': anomaly['ts_code'],
                'name': anomaly['name'],
                'alert_type': alert_type,
                'current_price': anomaly['current_price'],
                'change_pct': anomaly['change_pct'],
                'volume_ratio': anomaly['volume_ratio'],
                'alert_time': anomaly['update_time'],
                'severity': 'high' if anomaly['anomaly_score'] > 50 else 'medium'
            })
        
        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts,
                'total_count': len(alerts),
                'update_time': anomalies_result.get('data', {}).get('update_time')
            },
            'message': f'获取到 {len(alerts)} 个价格预警'
        })
        
    except Exception as e:
        logger.error(f"获取价格预警失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/heatmap', methods=['GET'])
def get_market_heatmap():
    """获取市场热力图数据"""
    try:
        period_hours = int(request.args.get('period_hours', 1))
        
        # 获取板块表现数据
        sector_result = monitor_service.get_sector_performance(period_hours=period_hours)
        
        if not sector_result.get('success'):
            return jsonify(sector_result)
        
        # 转换为热力图格式
        heatmap_data = []
        sectors = sector_result.get('data', {}).get('sectors', [])
        
        for sector in sectors:
            heatmap_data.append({
                'name': sector['sector_name'],
                'value': sector['avg_change_pct'],
                'volume': sector['total_volume'],
                'stock_count': sector['stock_count'],
                'rising_ratio': sector['rising_ratio']
            })
        
        return jsonify({
            'success': True,
            'data': {
                'heatmap': heatmap_data,
                'period_hours': period_hours,
                'update_time': sector_result.get('data', {}).get('update_time')
            },
            'message': f'获取到 {len(heatmap_data)} 个板块的热力图数据'
        })
        
    except Exception as e:
        logger.error(f"获取市场热力图失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/top-movers', methods=['GET'])
def get_top_movers():
    """获取涨跌幅排行"""
    try:
        limit = int(request.args.get('limit', 20))
        period_type = request.args.get('period_type', '1min')
        
        # 获取实时行情数据
        quotes_result = monitor_service.get_realtime_quotes(
            stock_codes=None,
            period_type=period_type,
            limit=100  # 获取更多数据用于排序
        )
        
        if not quotes_result.get('success'):
            return jsonify(quotes_result)
        
        quotes = quotes_result.get('data', {}).get('quotes', [])
        
        # 按涨跌幅排序
        quotes.sort(key=lambda x: x['change_pct'], reverse=True)
        
        # 分别获取涨幅榜和跌幅榜
        top_gainers = quotes[:limit]
        top_losers = sorted(quotes, key=lambda x: x['change_pct'])[:limit]
        
        # 按成交量排序获取活跃股票
        most_active = sorted(quotes, key=lambda x: x['volume'], reverse=True)[:limit]
        
        return jsonify({
            'success': True,
            'data': {
                'top_gainers': top_gainers,
                'top_losers': top_losers,
                'most_active': most_active,
                'update_time': quotes_result.get('data', {}).get('update_time')
            },
            'message': f'获取涨跌幅排行成功'
        })
        
    except Exception as e:
        logger.error(f"获取涨跌幅排行失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_monitor_bp.route('/market-stats', methods=['GET'])
def get_market_stats():
    """获取市场统计数据"""
    try:
        period_hours = int(request.args.get('period_hours', 1))
        
        # 获取市场情绪数据
        sentiment_result = monitor_service.get_market_sentiment(period_hours=period_hours)
        
        if not sentiment_result.get('success'):
            return jsonify(sentiment_result)
        
        sentiment_data = sentiment_result.get('data', {})
        
        # 获取异动股票数量
        anomalies_result = monitor_service.detect_anomalies(
            change_threshold=3.0,
            volume_threshold=2.0,
            period_hours=period_hours
        )
        
        anomaly_count = 0
        if anomalies_result.get('success'):
            anomaly_count = anomalies_result.get('data', {}).get('total_count', 0)
        
        # 组合统计数据
        stats = {
            'market_sentiment': {
                'score': sentiment_data.get('sentiment_score', 0),
                'status': sentiment_data.get('market_status', '未知'),
                'status_color': sentiment_data.get('status_color', 'secondary')
            },
            'stock_stats': {
                'total_stocks': sentiment_data.get('total_stocks', 0),
                'rising_stocks': sentiment_data.get('rising_stocks', 0),
                'falling_stocks': sentiment_data.get('falling_stocks', 0),
                'unchanged_stocks': sentiment_data.get('unchanged_stocks', 0),
                'rising_ratio': sentiment_data.get('rising_ratio', 0)
            },
            'trading_stats': {
                'total_volume': sentiment_data.get('total_volume', 0),
                'total_amount': sentiment_data.get('total_amount', 0),
                'avg_change_pct': sentiment_data.get('avg_change_pct', 0),
                'volatility': sentiment_data.get('volatility', 0)
            },
            'anomaly_count': anomaly_count,
            'period_hours': period_hours,
            'update_time': sentiment_data.get('update_time')
        }
        
        return jsonify({
            'success': True,
            'data': stats,
            'message': '市场统计数据获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取市场统计数据失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}) 