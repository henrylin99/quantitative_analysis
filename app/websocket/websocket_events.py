"""
WebSocket事件处理器
提供实时数据推送功能
"""

import logging
from datetime import datetime
from flask import request
from flask_socketio import emit, join_room, leave_room, disconnect
from app.extensions import socketio
from app.services.realtime_data_manager import RealtimeDataManager
from app.services.realtime_indicator_engine import RealtimeIndicatorEngine
from app.services.realtime_trading_signal_engine import RealtimeTradingSignalEngine
from app.services.realtime_monitor_service import RealtimeMonitorService
from app.services.realtime_risk_manager import RealtimeRiskManager

logger = logging.getLogger(__name__)

# 连接管理
connected_clients = {}
room_subscriptions = {}

@socketio.on('connect')
def handle_connect():
    """客户端连接事件"""
    client_id = request.sid
    connected_clients[client_id] = {
        'connected_at': datetime.now(),
        'subscriptions': set(),
        'user_agent': request.headers.get('User-Agent', ''),
        'remote_addr': request.remote_addr
    }
    
    logger.info(f"客户端连接: {client_id} from {request.remote_addr}")
    
    # 发送连接确认
    emit('connected', {
        'client_id': client_id,
        'server_time': datetime.now().isoformat(),
        'message': '连接成功'
    })

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开连接事件"""
    client_id = request.sid
    
    if client_id in connected_clients:
        # 清理订阅
        subscriptions = connected_clients[client_id]['subscriptions']
        for subscription in subscriptions:
            if subscription in room_subscriptions:
                room_subscriptions[subscription].discard(client_id)
                if not room_subscriptions[subscription]:
                    del room_subscriptions[subscription]
        
        del connected_clients[client_id]
        logger.info(f"客户端断开连接: {client_id}")

@socketio.on('subscribe')
def handle_subscribe(data):
    """订阅数据推送"""
    client_id = request.sid
    subscription_type = data.get('type')
    params = data.get('params', {})
    
    if client_id not in connected_clients:
        emit('error', {'message': '客户端未连接'})
        return
    
    # 支持的订阅类型
    valid_types = [
        'market_data',      # 市场数据
        'indicators',       # 技术指标
        'signals',          # 交易信号
        'monitor',          # 实时监控
        'risk_alerts',      # 风险预警
        'portfolio',        # 投资组合
        'news'              # 新闻资讯
    ]
    
    if subscription_type not in valid_types:
        emit('error', {'message': f'不支持的订阅类型: {subscription_type}'})
        return
    
    # 创建房间名称
    room_name = f"{subscription_type}_{params.get('symbol', 'all')}"
    
    # 加入房间
    join_room(room_name)
    
    # 记录订阅
    connected_clients[client_id]['subscriptions'].add(room_name)
    if room_name not in room_subscriptions:
        room_subscriptions[room_name] = set()
    room_subscriptions[room_name].add(client_id)
    
    logger.info(f"客户端 {client_id} 订阅: {subscription_type} - {params}")
    
    emit('subscribed', {
        'type': subscription_type,
        'params': params,
        'room': room_name,
        'message': '订阅成功'
    })

@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    """取消订阅"""
    client_id = request.sid
    subscription_type = data.get('type')
    params = data.get('params', {})
    
    room_name = f"{subscription_type}_{params.get('symbol', 'all')}"
    
    # 离开房间
    leave_room(room_name)
    
    # 清理订阅记录
    if client_id in connected_clients:
        connected_clients[client_id]['subscriptions'].discard(room_name)
    
    if room_name in room_subscriptions:
        room_subscriptions[room_name].discard(client_id)
        if not room_subscriptions[room_name]:
            del room_subscriptions[room_name]
    
    logger.info(f"客户端 {client_id} 取消订阅: {subscription_type} - {params}")
    
    emit('unsubscribed', {
        'type': subscription_type,
        'params': params,
        'room': room_name,
        'message': '取消订阅成功'
    })

@socketio.on('ping')
def handle_ping():
    """心跳检测"""
    emit('pong', {'timestamp': datetime.now().isoformat()})

@socketio.on('get_status')
def handle_get_status():
    """获取连接状态"""
    client_id = request.sid
    
    if client_id in connected_clients:
        client_info = connected_clients[client_id]
        emit('status', {
            'client_id': client_id,
            'connected_at': client_info['connected_at'].isoformat(),
            'subscriptions': list(client_info['subscriptions']),
            'total_clients': len(connected_clients),
            'total_rooms': len(room_subscriptions)
        })
    else:
        emit('error', {'message': '客户端信息未找到'})

# 数据推送函数
def broadcast_market_data(symbol, data):
    """广播市场数据"""
    room_name = f"market_data_{symbol}"
    if room_name in room_subscriptions:
        socketio.emit('market_data_update', {
            'symbol': symbol,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

def broadcast_indicators(symbol, indicators):
    """广播技术指标数据"""
    room_name = f"indicators_{symbol}"
    if room_name in room_subscriptions:
        socketio.emit('indicators_update', {
            'symbol': symbol,
            'indicators': indicators,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

def broadcast_signals(symbol, signals):
    """广播交易信号"""
    room_name = f"signals_{symbol}"
    if room_name in room_subscriptions:
        socketio.emit('signals_update', {
            'symbol': symbol,
            'signals': signals,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

def broadcast_monitor_data(data):
    """广播监控数据"""
    room_name = "monitor_all"
    if room_name in room_subscriptions:
        socketio.emit('monitor_update', {
            'data': data,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

def broadcast_risk_alert(alert):
    """广播风险预警"""
    room_name = f"risk_alerts_{alert.get('portfolio_id', 'all')}"
    if room_name in room_subscriptions:
        socketio.emit('risk_alert', {
            'alert': alert,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

def broadcast_portfolio_update(portfolio_id, data):
    """广播投资组合更新"""
    room_name = f"portfolio_{portfolio_id}"
    if room_name in room_subscriptions:
        socketio.emit('portfolio_update', {
            'portfolio_id': portfolio_id,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

def broadcast_news(news):
    """广播新闻资讯"""
    room_name = "news_all"
    if room_name in room_subscriptions:
        socketio.emit('news_update', {
            'news': news,
            'timestamp': datetime.now().isoformat()
        }, room=room_name)

# 获取连接统计信息
def get_connection_stats():
    """获取连接统计信息"""
    return {
        'total_clients': len(connected_clients),
        'total_rooms': len(room_subscriptions),
        'room_details': {
            room: len(clients) for room, clients in room_subscriptions.items()
        },
        'client_details': {
            client_id: {
                'connected_at': info['connected_at'].isoformat(),
                'subscriptions_count': len(info['subscriptions']),
                'remote_addr': info['remote_addr']
            } for client_id, info in connected_clients.items()
        }
    } 