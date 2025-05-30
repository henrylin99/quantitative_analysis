"""
实时分析报告管理API接口
提供报告生成、模板管理和订阅功能
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.services.realtime_report_generator import RealtimeReportGenerator
from app.models.realtime_report import ReportTemplate, RealtimeReport, ReportSubscription
from app.extensions import db

logger = logging.getLogger(__name__)

# 创建蓝图
realtime_report_bp = Blueprint('realtime_report', __name__)

# 初始化服务
report_generator = RealtimeReportGenerator()


@realtime_report_bp.route('/generate-report', methods=['POST'])
def generate_report():
    """生成报告"""
    try:
        data = request.get_json()
        
        report_type = data.get('report_type', 'daily_summary')
        template_id = data.get('template_id')
        report_name = data.get('report_name')
        parameters = data.get('parameters', {})
        generated_by = data.get('generated_by', 'user')
        
        # 验证报告类型
        valid_types = ['daily_summary', 'portfolio_analysis', 'risk_assessment', 
                      'signal_analysis', 'market_overview', 'custom']
        if report_type not in valid_types:
            return jsonify({
                'success': False,
                'message': f'无效的报告类型，支持的类型: {", ".join(valid_types)}'
            }), 400
        
        # 生成报告
        result = report_generator.generate_report(
            report_type=report_type,
            template_id=template_id,
            report_name=report_name,
            parameters=parameters,
            generated_by=generated_by
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"生成报告API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/reports', methods=['GET'])
def get_reports():
    """获取报告列表"""
    try:
        report_type = request.args.get('report_type')
        limit = int(request.args.get('limit', 50))
        
        result = report_generator.get_reports(report_type, limit)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取报告列表API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/reports/<int:report_id>', methods=['GET'])
def get_report_by_id(report_id):
    """根据ID获取报告"""
    try:
        result = report_generator.get_report_by_id(report_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取报告API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/reports/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    """删除报告"""
    try:
        report = RealtimeReport.query.get(report_id)
        
        if not report:
            return jsonify({'success': False, 'message': '报告不存在'}), 404
        
        db.session.delete(report)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '报告删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除报告API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/templates', methods=['GET'])
def get_report_templates():
    """获取报告模板"""
    try:
        template_type = request.args.get('template_type')
        
        result = report_generator.get_report_templates(template_type)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取报告模板API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/templates', methods=['POST'])
def create_report_template():
    """创建报告模板"""
    try:
        data = request.get_json()
        
        template_name = data.get('template_name')
        template_type = data.get('template_type')
        description = data.get('description')
        components = data.get('components', [])
        created_by = data.get('created_by', 'user')
        
        if not template_name or not template_type:
            return jsonify({
                'success': False,
                'message': '模板名称和类型不能为空'
            }), 400
        
        result = report_generator.create_report_template(
            template_name=template_name,
            template_type=template_type,
            description=description,
            components=components,
            created_by=created_by
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"创建报告模板API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/templates/<int:template_id>', methods=['GET'])
def get_template_by_id(template_id):
    """根据ID获取模板"""
    try:
        template = ReportTemplate.query.get(template_id)
        
        if not template:
            return jsonify({'success': False, 'message': '模板不存在'}), 404
        
        return jsonify({
            'success': True,
            'data': template.to_dict(),
            'message': '模板获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取模板API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/templates/<int:template_id>', methods=['PUT'])
def update_report_template(template_id):
    """更新报告模板"""
    try:
        template = ReportTemplate.query.get(template_id)
        
        if not template:
            return jsonify({'success': False, 'message': '模板不存在'}), 404
        
        data = request.get_json()
        
        # 更新模板字段
        if 'template_name' in data:
            template.template_name = data['template_name']
        if 'description' in data:
            template.description = data['description']
        if 'components' in data:
            import json
            template.components = json.dumps(data['components'])
        if 'is_active' in data:
            template.is_active = data['is_active']
        if 'is_default' in data:
            template.is_default = data['is_default']
        
        template.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': template.to_dict(),
            'message': '模板更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新模板API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/templates/<int:template_id>', methods=['DELETE'])
def delete_report_template(template_id):
    """删除报告模板"""
    try:
        template = ReportTemplate.query.get(template_id)
        
        if not template:
            return jsonify({'success': False, 'message': '模板不存在'}), 404
        
        # 检查是否有关联的报告
        report_count = RealtimeReport.query.filter_by(template_id=template_id).count()
        if report_count > 0:
            return jsonify({
                'success': False,
                'message': f'模板被 {report_count} 个报告使用，无法删除'
            }), 400
        
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '模板删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除模板API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/subscriptions', methods=['GET'])
def get_subscriptions():
    """获取订阅列表"""
    try:
        subscriptions = ReportSubscription.query.order_by(
            ReportSubscription.created_at.desc()
        ).all()
        
        return jsonify({
            'success': True,
            'data': [sub.to_dict() for sub in subscriptions],
            'message': f'获取到 {len(subscriptions)} 个订阅'
        })
        
    except Exception as e:
        logger.error(f"获取订阅列表API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
    """创建报告订阅"""
    try:
        data = request.get_json()
        
        subscription_name = data.get('subscription_name')
        template_id = data.get('template_id')
        subscriber_email = data.get('subscriber_email')
        subscriber_phone = data.get('subscriber_phone')
        schedule_type = data.get('schedule_type', 'daily')
        schedule_config = data.get('schedule_config', {})
        notification_channels = data.get('notification_channels', ['email'])
        created_by = data.get('created_by', 'user')
        
        if not subscription_name or not template_id:
            return jsonify({
                'success': False,
                'message': '订阅名称和模板ID不能为空'
            }), 400
        
        # 验证模板是否存在
        template = ReportTemplate.query.get(template_id)
        if not template:
            return jsonify({
                'success': False,
                'message': '指定的模板不存在'
            }), 400
        
        # 创建订阅
        subscription = ReportSubscription.create_subscription(
            subscription_name=subscription_name,
            template_id=template_id,
            subscriber_email=subscriber_email,
            subscriber_phone=subscriber_phone,
            schedule_type=schedule_type,
            schedule_config=schedule_config,
            notification_channels=notification_channels,
            created_by=created_by
        )
        
        return jsonify({
            'success': True,
            'data': subscription.to_dict(),
            'message': '订阅创建成功'
        })
        
    except Exception as e:
        logger.error(f"创建订阅API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/subscriptions/<int:subscription_id>', methods=['GET'])
def get_subscription_by_id(subscription_id):
    """根据ID获取订阅"""
    try:
        subscription = ReportSubscription.query.get(subscription_id)
        
        if not subscription:
            return jsonify({'success': False, 'message': '订阅不存在'}), 404
        
        return jsonify({
            'success': True,
            'data': subscription.to_dict(),
            'message': '订阅获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取订阅API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/subscriptions/<int:subscription_id>', methods=['PUT'])
def update_subscription(subscription_id):
    """更新订阅"""
    try:
        subscription = ReportSubscription.query.get(subscription_id)
        
        if not subscription:
            return jsonify({'success': False, 'message': '订阅不存在'}), 404
        
        data = request.get_json()
        
        # 更新订阅字段
        if 'subscription_name' in data:
            subscription.subscription_name = data['subscription_name']
        if 'subscriber_email' in data:
            subscription.subscriber_email = data['subscriber_email']
        if 'subscriber_phone' in data:
            subscription.subscriber_phone = data['subscriber_phone']
        if 'schedule_type' in data:
            subscription.schedule_type = data['schedule_type']
        if 'schedule_config' in data:
            import json
            subscription.schedule_config = json.dumps(data['schedule_config'])
        if 'notification_channels' in data:
            import json
            subscription.notification_channels = json.dumps(data['notification_channels'])
        if 'is_active' in data:
            subscription.is_active = data['is_active']
        
        subscription.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': subscription.to_dict(),
            'message': '订阅更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新订阅API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """删除订阅"""
    try:
        subscription = ReportSubscription.query.get(subscription_id)
        
        if not subscription:
            return jsonify({'success': False, 'message': '订阅不存在'}), 404
        
        db.session.delete(subscription)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '订阅删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除订阅API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/report-types', methods=['GET'])
def get_report_types():
    """获取支持的报告类型"""
    try:
        report_types = {
            'daily_summary': '每日市场总结',
            'portfolio_analysis': '投资组合分析',
            'risk_assessment': '风险评估报告',
            'signal_analysis': '交易信号分析',
            'market_overview': '市场概览报告',
            'custom': '自定义报告'
        }
        
        return jsonify({
            'success': True,
            'data': report_types,
            'message': f'支持 {len(report_types)} 种报告类型'
        })
        
    except Exception as e:
        logger.error(f"获取报告类型API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/schedule-types', methods=['GET'])
def get_schedule_types():
    """获取支持的调度类型"""
    try:
        schedule_types = {
            'daily': '每日',
            'weekly': '每周',
            'monthly': '每月',
            'custom': '自定义'
        }
        
        return jsonify({
            'success': True,
            'data': schedule_types,
            'message': f'支持 {len(schedule_types)} 种调度类型'
        })
        
    except Exception as e:
        logger.error(f"获取调度类型API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@realtime_report_bp.route('/statistics', methods=['GET'])
def get_report_statistics():
    """获取报告统计信息"""
    try:
        # 统计报告数量
        total_reports = RealtimeReport.query.count()
        completed_reports = RealtimeReport.query.filter_by(report_status='completed').count()
        failed_reports = RealtimeReport.query.filter_by(report_status='failed').count()
        
        # 统计模板数量
        total_templates = ReportTemplate.query.count()
        active_templates = ReportTemplate.query.filter_by(is_active=True).count()
        
        # 统计订阅数量
        total_subscriptions = ReportSubscription.query.count()
        active_subscriptions = ReportSubscription.query.filter_by(is_active=True).count()
        
        # 按类型统计报告
        from sqlalchemy import func
        report_type_stats = db.session.query(
            RealtimeReport.report_type,
            func.count(RealtimeReport.id).label('count')
        ).group_by(RealtimeReport.report_type).all()
        
        return jsonify({
            'success': True,
            'data': {
                'reports': {
                    'total': total_reports,
                    'completed': completed_reports,
                    'failed': failed_reports,
                    'success_rate': (completed_reports / total_reports * 100) if total_reports > 0 else 0
                },
                'templates': {
                    'total': total_templates,
                    'active': active_templates
                },
                'subscriptions': {
                    'total': total_subscriptions,
                    'active': active_subscriptions
                },
                'report_type_stats': {
                    stat.report_type: stat.count for stat in report_type_stats
                }
            },
            'message': '统计信息获取成功'
        })
        
    except Exception as e:
        logger.error(f"获取报告统计API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500 