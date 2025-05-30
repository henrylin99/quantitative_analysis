"""
WebSocket管理API
提供WebSocket连接管理和推送配置功能
"""

from flask import Blueprint, request, jsonify
from app.services.websocket_push_service import push_service
from app.websocket.websocket_events import get_connection_stats
import logging

logger = logging.getLogger(__name__)

websocket_api_bp = Blueprint('websocket_api', __name__)

@websocket_api_bp.route('/status', methods=['GET'])
def get_websocket_status():
    """获取WebSocket服务状态"""
    try:
        status = push_service.get_push_status()
        
        return jsonify({
            'success': True,
            'data': status,
            'message': 'WebSocket状态获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取WebSocket状态失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取WebSocket状态失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/connections', methods=['GET'])
def get_connections():
    """获取连接统计信息"""
    try:
        stats = get_connection_stats()
        
        return jsonify({
            'success': True,
            'data': stats,
            'message': '连接信息获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取连接信息失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取连接信息失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/push-config', methods=['GET'])
def get_push_config():
    """获取推送配置"""
    try:
        config = push_service.push_config
        
        return jsonify({
            'success': True,
            'data': config,
            'message': '推送配置获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取推送配置失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取推送配置失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/push-config', methods=['PUT'])
def update_push_config():
    """更新推送配置"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': '请提供配置数据'
            }), 400
        
        # 验证配置格式
        valid_types = ['market_data', 'indicators', 'signals', 'monitor', 'risk_alerts', 'portfolio', 'news']
        for data_type, config in data.items():
            if data_type not in valid_types:
                return jsonify({
                    'success': False,
                    'message': f'不支持的数据类型: {data_type}'
                }), 400
            
            if not isinstance(config, dict):
                return jsonify({
                    'success': False,
                    'message': f'配置格式错误: {data_type}'
                }), 400
        
        # 更新配置
        push_service.update_push_config(data)
        
        return jsonify({
            'success': True,
            'data': push_service.push_config,
            'message': '推送配置更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新推送配置失败: {e}")
        return jsonify({
            'success': False,
            'message': f'更新推送配置失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/start', methods=['POST'])
def start_push_service():
    """启动推送服务"""
    try:
        push_service.start_push_service()
        
        return jsonify({
            'success': True,
            'message': '推送服务启动成功'
        })
        
    except Exception as e:
        logger.error(f"启动推送服务失败: {e}")
        return jsonify({
            'success': False,
            'message': f'启动推送服务失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/stop', methods=['POST'])
def stop_push_service():
    """停止推送服务"""
    try:
        push_service.stop_push_service()
        
        return jsonify({
            'success': True,
            'message': '推送服务停止成功'
        })
        
    except Exception as e:
        logger.error(f"停止推送服务失败: {e}")
        return jsonify({
            'success': False,
            'message': f'停止推送服务失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/push', methods=['POST'])
def trigger_push():
    """触发立即推送"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': '请提供推送数据'
            }), 400
        
        data_type = data.get('type')
        push_data = data.get('data')
        
        if not data_type or not push_data:
            return jsonify({
                'success': False,
                'message': '请提供数据类型和推送数据'
            }), 400
        
        # 触发推送
        push_service.trigger_immediate_push(data_type, push_data)
        
        return jsonify({
            'success': True,
            'message': f'{data_type}数据推送成功'
        })
        
    except Exception as e:
        logger.error(f"触发推送失败: {e}")
        return jsonify({
            'success': False,
            'message': f'触发推送失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/test-connection', methods=['POST'])
def test_connection():
    """测试WebSocket连接"""
    try:
        # 发送测试消息
        test_data = {
            'type': 'test',
            'message': 'WebSocket连接测试',
            'timestamp': push_service.get_push_status()['connection_stats']
        }
        
        push_service.trigger_immediate_push('monitor', test_data)
        
        return jsonify({
            'success': True,
            'data': test_data,
            'message': '测试消息发送成功'
        })
        
    except Exception as e:
        logger.error(f"测试连接失败: {e}")
        return jsonify({
            'success': False,
            'message': f'测试连接失败: {str(e)}'
        }), 500

@websocket_api_bp.route('/supported-types', methods=['GET'])
def get_supported_types():
    """获取支持的推送类型"""
    try:
        supported_types = {
            'market_data': {
                'name': '市场数据',
                'description': '实时股票价格、成交量等市场数据',
                'default_interval': 30
            },
            'indicators': {
                'name': '技术指标',
                'description': '实时技术指标计算结果',
                'default_interval': 60
            },
            'signals': {
                'name': '交易信号',
                'description': '实时交易信号和策略建议',
                'default_interval': 60
            },
            'monitor': {
                'name': '实时监控',
                'description': '市场监控、异动检测等数据',
                'default_interval': 30
            },
            'risk_alerts': {
                'name': '风险预警',
                'description': '投资组合风险预警信息',
                'default_interval': 60
            },
            'portfolio': {
                'name': '投资组合',
                'description': '投资组合更新和指标变化',
                'default_interval': 120
            },
            'news': {
                'name': '新闻资讯',
                'description': '市场新闻和资讯推送',
                'default_interval': 300
            }
        }
        
        return jsonify({
            'success': True,
            'data': supported_types,
            'message': '支持的推送类型获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取支持的推送类型失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取支持的推送类型失败: {str(e)}'
        }), 500 