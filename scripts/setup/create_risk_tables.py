#!/usr/bin/env python3
"""
创建风险管理和报告管理模块数据表
"""

from app import create_app
from app.extensions import db
from app.models.portfolio_position import PortfolioPosition
from app.models.risk_alert import RiskAlert
from app.models.realtime_report import ReportTemplate, RealtimeReport, ReportSubscription

def create_risk_tables():
    """创建风险管理和报告管理相关的数据表"""
    app = create_app()
    with app.app_context():
        try:
            # 创建所有表
            db.create_all()
            print('✅ 风险管理和报告管理数据表创建成功')
            
            # 验证表是否创建成功
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            required_tables = [
                'portfolio_positions', 
                'risk_alerts',
                'report_templates',
                'realtime_reports', 
                'report_subscriptions'
            ]
            
            for table in required_tables:
                if table in tables:
                    print(f'✅ 表 {table} 创建成功')
                else:
                    print(f'❌ 表 {table} 创建失败')
            
            # 创建一些示例数据
            create_sample_data()
            
        except Exception as e:
            print(f'❌ 创建数据表失败: {str(e)}')

def create_sample_data():
    """创建示例数据"""
    try:
        # 创建示例投资组合持仓
        sample_positions = [
            {
                'portfolio_id': 'demo_portfolio',
                'ts_code': '000001.SZ',
                'position_size': 1000,
                'avg_cost': 15.50,
                'current_price': 16.20,
                'sector': '银行'
            },
            {
                'portfolio_id': 'demo_portfolio', 
                'ts_code': '000002.SZ',
                'position_size': 500,
                'avg_cost': 28.30,
                'current_price': 27.80,
                'sector': '房地产'
            },
            {
                'portfolio_id': 'demo_portfolio',
                'ts_code': '600000.SH', 
                'position_size': 800,
                'avg_cost': 12.80,
                'current_price': 13.50,
                'sector': '银行'
            }
        ]
        
        for pos_data in sample_positions:
            existing = PortfolioPosition.query.filter_by(
                portfolio_id=pos_data['portfolio_id'],
                ts_code=pos_data['ts_code']
            ).first()
            
            if not existing:
                position = PortfolioPosition(
                    portfolio_id=pos_data['portfolio_id'],
                    ts_code=pos_data['ts_code'],
                    position_size=pos_data['position_size'],
                    avg_cost=pos_data['avg_cost'],
                    current_price=pos_data['current_price'],
                    market_value=pos_data['position_size'] * pos_data['current_price'],
                    unrealized_pnl=(pos_data['current_price'] - pos_data['avg_cost']) * pos_data['position_size'],
                    sector=pos_data['sector']
                )
                db.session.add(position)
        
        # 创建默认报告模板
        default_templates = [
            {
                'template_name': '默认每日总结模板',
                'template_type': 'daily_summary',
                'description': '系统默认的每日市场总结报告模板',
                'is_default': True
            },
            {
                'template_name': '默认投资组合分析模板',
                'template_type': 'portfolio_analysis', 
                'description': '系统默认的投资组合分析报告模板',
                'is_default': True
            },
            {
                'template_name': '默认风险评估模板',
                'template_type': 'risk_assessment',
                'description': '系统默认的风险评估报告模板', 
                'is_default': True
            }
        ]
        
        for template_data in default_templates:
            existing = ReportTemplate.query.filter_by(
                template_type=template_data['template_type'],
                is_default=True
            ).first()
            
            if not existing:
                template = ReportTemplate(
                    template_name=template_data['template_name'],
                    template_type=template_data['template_type'],
                    description=template_data['description'],
                    is_default=template_data['is_default'],
                    created_by='system'
                )
                db.session.add(template)
        
        db.session.commit()
        print('✅ 示例数据创建成功')
        
    except Exception as e:
        print(f'❌ 创建示例数据失败: {str(e)}')
        db.session.rollback()

if __name__ == "__main__":
    create_risk_tables() 