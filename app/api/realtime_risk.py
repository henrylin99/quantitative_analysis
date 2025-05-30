"""
实时风险管理API接口
提供风险计算、监控、预警和止损止盈管理功能
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.services.realtime_risk_manager import RealtimeRiskManager
from app.models.portfolio_position import PortfolioPosition
from app.models.risk_alert import RiskAlert
from app.extensions import db

logger = logging.getLogger(__name__)

# 创建蓝图
realtime_risk_bp = Blueprint('realtime_risk', __name__)

# 初始化风险管理服务
risk_manager = RealtimeRiskManager()


@realtime_risk_bp.route('/portfolio-risk', methods=['POST'])
def calculate_portfolio_risk():
    """计算投资组合风险指标"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        period_days = data.get('period_days', 252)
        
        if not portfolio_id:
            return jsonify({'success': False, 'message': '组合ID不能为空'})
        
        result = risk_manager.calculate_portfolio_risk(portfolio_id, period_days)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"计算组合风险失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/position-monitor', methods=['GET'])
def monitor_position_risk():
    """监控持仓风险"""
    try:
        portfolio_id = request.args.get('portfolio_id')
        
        if not portfolio_id:
            return jsonify({'success': False, 'message': '组合ID不能为空'})
        
        result = risk_manager.monitor_position_risk(portfolio_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"监控持仓风险失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/stop-loss-take-profit', methods=['POST'])
def manage_stop_loss_take_profit():
    """管理止损止盈"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        stop_loss_method = data.get('stop_loss_method', 'percentage')
        stop_loss_value = float(data.get('stop_loss_value', 0.10))
        take_profit_method = data.get('take_profit_method', 'percentage')
        take_profit_value = float(data.get('take_profit_value', 0.20))
        
        if not portfolio_id:
            return jsonify({'success': False, 'message': '组合ID不能为空'})
        
        result = risk_manager.manage_stop_loss_take_profit(
            portfolio_id=portfolio_id,
            stop_loss_method=stop_loss_method,
            stop_loss_value=stop_loss_value,
            take_profit_method=take_profit_method,
            take_profit_value=take_profit_value
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"管理止损止盈失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/alerts', methods=['GET'])
def get_risk_alerts():
    """获取风险预警"""
    try:
        portfolio_id = request.args.get('portfolio_id')
        alert_level = request.args.get('alert_level')
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        result = risk_manager.get_risk_alerts(
            portfolio_id=portfolio_id,
            alert_level=alert_level,
            active_only=active_only
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取风险预警失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/alerts', methods=['POST'])
def create_risk_alert():
    """创建风险预警"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        alert_type = data.get('alert_type')
        alert_level = data.get('alert_level')
        alert_message = data.get('alert_message')
        risk_value = data.get('risk_value')
        threshold_value = data.get('threshold_value')
        
        if not all([ts_code, alert_type, alert_level, alert_message]):
            return jsonify({'success': False, 'message': '必填字段不能为空'})
        
        result = risk_manager.create_risk_alert(
            ts_code=ts_code,
            alert_type=alert_type,
            alert_level=alert_level,
            alert_message=alert_message,
            risk_value=risk_value,
            threshold_value=threshold_value
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"创建风险预警失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/alerts/<int:alert_id>/resolve', methods=['PUT'])
def resolve_risk_alert(alert_id):
    """解决风险预警"""
    try:
        alert = RiskAlert.query.get(alert_id)
        
        if not alert:
            return jsonify({'success': False, 'message': '预警记录不存在'})
        
        alert.resolve_alert()
        
        return jsonify({
            'success': True,
            'data': alert.to_dict(),
            'message': '预警已解决'
        })
        
    except Exception as e:
        logger.error(f"解决风险预警失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/portfolio', methods=['POST'])
def create_portfolio_position():
    """创建投资组合持仓"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        ts_code = data.get('ts_code')
        position_size = float(data.get('position_size'))
        avg_cost = float(data.get('avg_cost'))
        sector = data.get('sector')
        
        if not all([portfolio_id, ts_code, position_size, avg_cost]):
            return jsonify({'success': False, 'message': '必填字段不能为空'})
        
        # 检查是否已存在
        existing_position = PortfolioPosition.get_position_by_stock(portfolio_id, ts_code)
        if existing_position:
            return jsonify({'success': False, 'message': '该股票持仓已存在'})
        
        # 创建持仓
        position = PortfolioPosition(
            portfolio_id=portfolio_id,
            ts_code=ts_code,
            position_size=position_size,
            avg_cost=avg_cost,
            current_price=avg_cost,  # 初始价格设为成本价
            market_value=position_size * avg_cost,
            sector=sector
        )
        
        db.session.add(position)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': position.to_dict(),
            'message': '持仓创建成功'
        })
        
    except Exception as e:
        logger.error(f"创建持仓失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/portfolio/<portfolio_id>/positions', methods=['GET'])
def get_portfolio_positions(portfolio_id):
    """获取投资组合持仓"""
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        positions = PortfolioPosition.get_portfolio_positions(portfolio_id, active_only)
        
        return jsonify({
            'success': True,
            'data': {
                'portfolio_id': portfolio_id,
                'positions': [pos.to_dict() for pos in positions],
                'total_positions': len(positions)
            },
            'message': f'获取到 {len(positions)} 个持仓'
        })
        
    except Exception as e:
        logger.error(f"获取持仓失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/portfolio/<portfolio_id>/metrics', methods=['GET'])
def get_portfolio_metrics(portfolio_id):
    """获取投资组合指标"""
    try:
        metrics = PortfolioPosition.calculate_portfolio_metrics(portfolio_id)
        
        if not metrics:
            return jsonify({'success': False, 'message': '组合中没有持仓数据'})
        
        return jsonify({
            'success': True,
            'data': metrics,
            'message': '组合指标计算成功'
        })
        
    except Exception as e:
        logger.error(f"获取组合指标失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/portfolio/<portfolio_id>/positions/<int:position_id>', methods=['PUT'])
def update_portfolio_position(portfolio_id, position_id):
    """更新投资组合持仓"""
    try:
        data = request.get_json()
        
        position = PortfolioPosition.query.filter_by(
            id=position_id,
            portfolio_id=portfolio_id
        ).first()
        
        if not position:
            return jsonify({'success': False, 'message': '持仓记录不存在'})
        
        # 更新字段
        if 'position_size' in data:
            position.position_size = float(data['position_size'])
        if 'avg_cost' in data:
            position.avg_cost = float(data['avg_cost'])
        if 'current_price' in data:
            position.current_price = float(data['current_price'])
        if 'sector' in data:
            position.sector = data['sector']
        if 'stop_loss_price' in data:
            position.stop_loss_price = float(data['stop_loss_price'])
        if 'take_profit_price' in data:
            position.take_profit_price = float(data['take_profit_price'])
        
        # 重新计算市值和盈亏
        if position.current_price:
            position.market_value = position.position_size * position.current_price
            position.unrealized_pnl = (position.current_price - position.avg_cost) * position.position_size
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': position.to_dict(),
            'message': '持仓更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新持仓失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/portfolio/<portfolio_id>/positions/<int:position_id>', methods=['DELETE'])
def delete_portfolio_position(portfolio_id, position_id):
    """删除投资组合持仓"""
    try:
        position = PortfolioPosition.query.filter_by(
            id=position_id,
            portfolio_id=portfolio_id
        ).first()
        
        if not position:
            return jsonify({'success': False, 'message': '持仓记录不存在'})
        
        # 软删除
        position.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '持仓删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除持仓失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/risk-thresholds', methods=['GET'])
def get_risk_thresholds():
    """获取风险阈值配置"""
    try:
        return jsonify({
            'success': True,
            'data': risk_manager.risk_thresholds,
            'message': '风险阈值获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取风险阈值失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/risk-thresholds', methods=['PUT'])
def update_risk_thresholds():
    """更新风险阈值配置"""
    try:
        data = request.get_json()
        
        # 更新阈值
        for key, value in data.items():
            if key in risk_manager.risk_thresholds:
                risk_manager.risk_thresholds[key] = float(value)
        
        return jsonify({
            'success': True,
            'data': risk_manager.risk_thresholds,
            'message': '风险阈值更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新风险阈值失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/batch-update-prices', methods=['POST'])
def batch_update_prices():
    """批量更新持仓价格"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        
        if not portfolio_id:
            return jsonify({'success': False, 'message': '组合ID不能为空'})
        
        positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
        updated_count = 0
        
        for position in positions:
            # 获取最新价格
            current_price = risk_manager._get_current_price(position.ts_code)
            if current_price:
                position.update_market_data(current_price)
                updated_count += 1
        
        return jsonify({
            'success': True,
            'data': {
                'portfolio_id': portfolio_id,
                'total_positions': len(positions),
                'updated_positions': updated_count
            },
            'message': f'成功更新 {updated_count} 个持仓的价格'
        })
        
    except Exception as e:
        logger.error(f"批量更新价格失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@realtime_risk_bp.route('/stress-test', methods=['POST'])
def run_stress_test():
    """运行压力测试"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        scenarios = data.get('scenarios', [])
        
        if not portfolio_id:
            return jsonify({'success': False, 'message': '组合ID不能为空'})
        
        if not scenarios:
            # 默认压力测试场景
            scenarios = [
                {'name': '市场下跌10%', 'market_shock': -0.10},
                {'name': '市场下跌20%', 'market_shock': -0.20},
                {'name': '波动率上升50%', 'volatility_shock': 0.50},
                {'name': '相关性上升至0.9', 'correlation_shock': 0.90}
            ]
        
        # 获取组合持仓
        positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
        
        if not positions:
            return jsonify({'success': False, 'message': '组合中没有持仓数据'})
        
        stress_results = []
        
        for scenario in scenarios:
            scenario_result = {
                'scenario_name': scenario['name'],
                'original_value': sum(pos.market_value or 0 for pos in positions),
                'stressed_value': 0,
                'pnl_change': 0,
                'pnl_percentage': 0
            }
            
            # 简化的压力测试计算
            if 'market_shock' in scenario:
                shock = scenario['market_shock']
                stressed_value = sum((pos.market_value or 0) * (1 + shock) for pos in positions)
                scenario_result['stressed_value'] = stressed_value
                scenario_result['pnl_change'] = stressed_value - scenario_result['original_value']
                scenario_result['pnl_percentage'] = scenario_result['pnl_change'] / scenario_result['original_value'] * 100
            
            stress_results.append(scenario_result)
        
        return jsonify({
            'success': True,
            'data': {
                'portfolio_id': portfolio_id,
                'test_date': datetime.now().isoformat(),
                'scenarios': stress_results,
                'worst_case': min(stress_results, key=lambda x: x['pnl_percentage']),
                'best_case': max(stress_results, key=lambda x: x['pnl_percentage'])
            },
            'message': f'压力测试完成，测试了 {len(scenarios)} 个场景'
        })
        
    except Exception as e:
        logger.error(f"压力测试失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}) 