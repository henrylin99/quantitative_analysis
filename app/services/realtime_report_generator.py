"""
实时分析报告生成服务
提供多种类型的分析报告生成功能
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from app.models.realtime_report import ReportTemplate, RealtimeReport, ReportSubscription
from app.models.stock_minute_data import StockMinuteData
from app.models.realtime_indicator import RealtimeIndicator
from app.models.trading_signal import TradingSignal
from app.models.portfolio_position import PortfolioPosition
from app.models.risk_alert import RiskAlert
from app.extensions import db

logger = logging.getLogger(__name__)


class RealtimeReportGenerator:
    """实时分析报告生成器"""
    
    def __init__(self):
        """初始化报告生成器"""
        self.report_types = {
            'daily_summary': '每日市场总结',
            'portfolio_analysis': '投资组合分析',
            'risk_assessment': '风险评估报告',
            'signal_analysis': '交易信号分析',
            'market_overview': '市场概览报告',
            'custom': '自定义报告'
        }
        
        # 默认模板配置
        self.default_templates = {
            'daily_summary': {
                'sections': ['market_summary', 'top_movers', 'sector_performance', 'technical_signals'],
                'charts': ['market_trend', 'volume_analysis', 'sector_heatmap'],
                'metrics': ['total_volume', 'advance_decline', 'new_highs_lows']
            },
            'portfolio_analysis': {
                'sections': ['portfolio_overview', 'performance_analysis', 'risk_metrics', 'holdings_breakdown'],
                'charts': ['performance_chart', 'allocation_pie', 'risk_return_scatter'],
                'metrics': ['total_value', 'daily_pnl', 'ytd_return', 'sharpe_ratio']
            },
            'risk_assessment': {
                'sections': ['risk_overview', 'var_analysis', 'stress_test', 'correlation_analysis'],
                'charts': ['var_chart', 'correlation_heatmap', 'stress_scenarios'],
                'metrics': ['portfolio_var', 'max_drawdown', 'beta', 'volatility']
            },
            'signal_analysis': {
                'sections': ['signal_summary', 'strategy_performance', 'active_signals', 'backtest_results'],
                'charts': ['signal_distribution', 'strategy_returns', 'signal_timeline'],
                'metrics': ['total_signals', 'win_rate', 'avg_return', 'signal_strength']
            },
            'market_overview': {
                'sections': ['market_indices', 'sector_analysis', 'market_breadth', 'sentiment_indicators'],
                'charts': ['index_performance', 'sector_rotation', 'breadth_indicators'],
                'metrics': ['market_cap', 'trading_volume', 'volatility_index', 'sentiment_score']
            }
        }
    
    def generate_report(self, report_type: str, template_id: Optional[int] = None,
                       report_name: Optional[str] = None, parameters: Dict = None,
                       generated_by: str = 'system') -> Dict[str, Any]:
        """
        生成报告
        
        Args:
            report_type: 报告类型
            template_id: 模板ID
            report_name: 报告名称
            parameters: 报告参数
            generated_by: 生成者
            
        Returns:
            生成结果
        """
        try:
            start_time = datetime.utcnow()
            
            # 验证报告类型
            if report_type not in self.report_types:
                return {
                    'success': False,
                    'message': f'不支持的报告类型: {report_type}'
                }
            
            # 获取或创建模板
            template = self._get_or_create_template(report_type, template_id)
            
            # 生成报告名称
            if not report_name:
                report_name = f"{self.report_types[report_type]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 创建报告记录
            report = RealtimeReport.create_report(
                report_name=report_name,
                report_type=report_type,
                template_id=template.id if template else None,
                generated_by=generated_by
            )
            
            # 收集报告数据
            report_data = self._collect_report_data(report_type, parameters or {})
            
            # 生成报告内容
            report_content = self._generate_report_content(report_type, template, report_data)
            
            # 更新报告
            generation_time = (datetime.utcnow() - start_time).total_seconds()
            report.report_content = json.dumps(report_content)
            report.report_data = json.dumps(report_data)
            report.update_status('completed', generation_time=generation_time)
            
            return {
                'success': True,
                'data': {
                    'report_id': report.id,
                    'report_name': report.report_name,
                    'report_type': report.report_type,
                    'generation_time': generation_time,
                    'content': report_content,
                    'data': report_data
                },
                'message': '报告生成成功'
            }
            
        except Exception as e:
            logger.error(f"生成报告失败: {str(e)}")
            if 'report' in locals():
                report.update_status('failed', error_message=str(e))
            return {
                'success': False,
                'message': f'报告生成失败: {str(e)}'
            }
    
    def _get_or_create_template(self, report_type: str, template_id: Optional[int]) -> Optional[ReportTemplate]:
        """获取或创建模板"""
        if template_id:
            template = ReportTemplate.query.get(template_id)
            if template and template.template_type == report_type:
                return template
        
        # 查找默认模板
        template = ReportTemplate.get_default_template(report_type)
        if template:
            return template
        
        # 创建默认模板
        if report_type in self.default_templates:
            template_config = self.default_templates[report_type]
            template = ReportTemplate.create_template(
                template_name=f"默认{self.report_types[report_type]}模板",
                template_type=report_type,
                description=f"系统自动生成的{self.report_types[report_type]}默认模板",
                template_config=template_config,
                components=template_config.get('sections', []),
                created_by='system'
            )
            template.is_default = True
            db.session.commit()
            return template
        
        return None
    
    def _collect_report_data(self, report_type: str, parameters: Dict) -> Dict[str, Any]:
        """收集报告数据"""
        data = {
            'generated_at': datetime.utcnow().isoformat(),
            'report_type': report_type,
            'parameters': parameters
        }
        
        try:
            if report_type == 'daily_summary':
                data.update(self._collect_daily_summary_data())
            elif report_type == 'portfolio_analysis':
                portfolio_id = parameters.get('portfolio_id', 'demo_portfolio')
                data.update(self._collect_portfolio_data(portfolio_id))
            elif report_type == 'risk_assessment':
                portfolio_id = parameters.get('portfolio_id', 'demo_portfolio')
                data.update(self._collect_risk_data(portfolio_id))
            elif report_type == 'signal_analysis':
                data.update(self._collect_signal_data())
            elif report_type == 'market_overview':
                data.update(self._collect_market_data())
            
        except Exception as e:
            logger.error(f"收集{report_type}数据失败: {str(e)}")
            data['error'] = str(e)
        
        return data
    
    def _collect_daily_summary_data(self) -> Dict[str, Any]:
        """收集每日总结数据"""
        today = datetime.now().date()
        
        # 获取今日分钟数据统计
        minute_data_count = StockMinuteData.query.filter(
            db.func.date(StockMinuteData.datetime) == today
        ).count()
        
        # 获取活跃股票数量
        active_stocks = db.session.query(StockMinuteData.ts_code).filter(
            db.func.date(StockMinuteData.datetime) == today
        ).distinct().count()
        
        # 获取技术指标数量
        indicator_count = RealtimeIndicator.query.filter(
            db.func.date(RealtimeIndicator.datetime) == today
        ).count()
        
        # 获取交易信号数量
        signal_count = TradingSignal.query.filter(
            db.func.date(TradingSignal.created_at) == today
        ).count()
        
        return {
            'date': today.isoformat(),
            'market_data': {
                'minute_data_points': minute_data_count,
                'active_stocks': active_stocks,
                'technical_indicators': indicator_count,
                'trading_signals': signal_count
            },
            'summary': {
                'total_activity': minute_data_count + indicator_count + signal_count,
                'data_coverage': f"{active_stocks}只股票" if active_stocks > 0 else "无数据"
            }
        }
    
    def _collect_portfolio_data(self, portfolio_id: str) -> Dict[str, Any]:
        """收集投资组合数据"""
        # 获取组合持仓
        positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
        
        if not positions:
            return {
                'portfolio_id': portfolio_id,
                'error': '组合中没有持仓数据'
            }
        
        # 计算组合指标
        metrics = PortfolioPosition.calculate_portfolio_metrics(portfolio_id)
        
        # 持仓分析
        holdings_data = []
        for position in positions:
            holdings_data.append({
                'ts_code': position.ts_code,
                'position_size': position.position_size,
                'market_value': position.market_value,
                'unrealized_pnl': position.unrealized_pnl,
                'weight': (position.market_value / metrics['total_market_value'] * 100) if metrics['total_market_value'] > 0 else 0,
                'sector': position.sector or '未分类'
            })
        
        return {
            'portfolio_id': portfolio_id,
            'metrics': metrics,
            'holdings': holdings_data,
            'position_count': len(positions),
            'analysis_date': datetime.utcnow().isoformat()
        }
    
    def _collect_risk_data(self, portfolio_id: str) -> Dict[str, Any]:
        """收集风险数据"""
        # 获取组合持仓
        positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
        
        if not positions:
            return {
                'portfolio_id': portfolio_id,
                'error': '组合中没有持仓数据'
            }
        
        # 获取风险预警
        alerts = RiskAlert.query.filter_by(is_resolved=False).all()
        
        # 计算基础风险指标
        total_value = sum(pos.market_value or 0 for pos in positions)
        total_pnl = sum(pos.unrealized_pnl or 0 for pos in positions)
        
        # 集中度风险
        max_position = max((pos.market_value or 0) for pos in positions) if positions else 0
        concentration_risk = (max_position / total_value * 100) if total_value > 0 else 0
        
        # 行业分布
        sector_exposure = {}
        for position in positions:
            sector = position.sector or '未分类'
            sector_exposure[sector] = sector_exposure.get(sector, 0) + (position.market_value or 0)
        
        return {
            'portfolio_id': portfolio_id,
            'risk_metrics': {
                'total_value': total_value,
                'total_pnl': total_pnl,
                'concentration_risk': concentration_risk,
                'position_count': len(positions),
                'active_alerts': len(alerts)
            },
            'sector_exposure': sector_exposure,
            'risk_alerts': [alert.to_dict() for alert in alerts[:10]],  # 最近10个预警
            'analysis_date': datetime.utcnow().isoformat()
        }
    
    def _collect_signal_data(self) -> Dict[str, Any]:
        """收集交易信号数据"""
        # 获取最近的交易信号
        recent_signals = TradingSignal.query.filter(
            TradingSignal.created_at >= datetime.utcnow() - timedelta(days=7)
        ).order_by(TradingSignal.created_at.desc()).limit(100).all()
        
        # 统计信号类型分布
        signal_types = {}
        strategy_performance = {}
        
        for signal in recent_signals:
            # 信号类型统计
            signal_type = signal.signal_type
            signal_types[signal_type] = signal_types.get(signal_type, 0) + 1
            
            # 策略表现统计
            strategy = signal.strategy_name
            if strategy not in strategy_performance:
                strategy_performance[strategy] = {
                    'count': 0,
                    'avg_strength': 0,
                    'total_strength': 0
                }
            
            strategy_performance[strategy]['count'] += 1
            strategy_performance[strategy]['total_strength'] += abs(signal.signal_strength or 0)
        
        # 计算平均强度
        for strategy in strategy_performance:
            count = strategy_performance[strategy]['count']
            if count > 0:
                strategy_performance[strategy]['avg_strength'] = \
                    strategy_performance[strategy]['total_strength'] / count
        
        return {
            'signal_summary': {
                'total_signals': len(recent_signals),
                'signal_types': signal_types,
                'strategy_performance': strategy_performance,
                'analysis_period': '最近7天'
            },
            'recent_signals': [signal.to_dict() for signal in recent_signals[:20]],  # 最近20个信号
            'analysis_date': datetime.utcnow().isoformat()
        }
    
    def _collect_market_data(self) -> Dict[str, Any]:
        """收集市场数据"""
        today = datetime.now().date()
        
        # 获取今日活跃股票
        active_stocks = db.session.query(
            StockMinuteData.ts_code,
            db.func.count(StockMinuteData.id).label('data_points'),
            db.func.max(StockMinuteData.close).label('high'),
            db.func.min(StockMinuteData.close).label('low'),
            db.func.sum(StockMinuteData.volume).label('total_volume')
        ).filter(
            db.func.date(StockMinuteData.datetime) == today
        ).group_by(StockMinuteData.ts_code).all()
        
        # 计算市场统计
        total_volume = sum(stock.total_volume or 0 for stock in active_stocks)
        avg_data_points = np.mean([stock.data_points for stock in active_stocks]) if active_stocks else 0
        
        # 获取技术指标统计
        indicator_stats = db.session.query(
            RealtimeIndicator.indicator_type,
            db.func.count(RealtimeIndicator.id).label('count')
        ).filter(
            db.func.date(RealtimeIndicator.datetime) == today
        ).group_by(RealtimeIndicator.indicator_type).all()
        
        return {
            'market_overview': {
                'active_stocks': len(active_stocks),
                'total_volume': total_volume,
                'avg_data_points': avg_data_points,
                'analysis_date': today.isoformat()
            },
            'stock_activity': [
                {
                    'ts_code': stock.ts_code,
                    'data_points': stock.data_points,
                    'high': stock.high,
                    'low': stock.low,
                    'total_volume': stock.total_volume
                }
                for stock in active_stocks[:20]  # 前20只活跃股票
            ],
            'indicator_distribution': {
                stat.indicator_type: stat.count for stat in indicator_stats
            }
        }
    
    def _generate_report_content(self, report_type: str, template: Optional[ReportTemplate], 
                               report_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成报告内容"""
        content = {
            'title': f"{self.report_types[report_type]} - {datetime.now().strftime('%Y年%m月%d日')}",
            'generated_at': datetime.utcnow().isoformat(),
            'report_type': report_type,
            'sections': []
        }
        
        # 根据报告类型生成内容
        if report_type == 'daily_summary':
            content['sections'] = self._generate_daily_summary_content(report_data)
        elif report_type == 'portfolio_analysis':
            content['sections'] = self._generate_portfolio_content(report_data)
        elif report_type == 'risk_assessment':
            content['sections'] = self._generate_risk_content(report_data)
        elif report_type == 'signal_analysis':
            content['sections'] = self._generate_signal_content(report_data)
        elif report_type == 'market_overview':
            content['sections'] = self._generate_market_content(report_data)
        
        return content
    
    def _generate_daily_summary_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成每日总结内容"""
        sections = []
        
        if 'market_data' in data:
            market_data = data['market_data']
            sections.append({
                'title': '市场数据概览',
                'type': 'summary',
                'content': f"今日共处理{market_data['minute_data_points']}个分钟数据点，"
                          f"覆盖{market_data['active_stocks']}只股票，"
                          f"生成{market_data['technical_indicators']}个技术指标，"
                          f"产生{market_data['trading_signals']}个交易信号。"
            })
        
        sections.append({
            'title': '数据质量评估',
            'type': 'metrics',
            'content': '数据接入正常，系统运行稳定。'
        })
        
        return sections
    
    def _generate_portfolio_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成投资组合内容"""
        sections = []
        
        if 'error' in data:
            sections.append({
                'title': '错误信息',
                'type': 'error',
                'content': data['error']
            })
            return sections
        
        if 'metrics' in data:
            metrics = data['metrics']
            sections.append({
                'title': '组合概览',
                'type': 'summary',
                'content': f"组合总市值: {metrics.get('total_market_value', 0):,.2f}，"
                          f"未实现盈亏: {metrics.get('total_unrealized_pnl', 0):,.2f}，"
                          f"持仓数量: {data.get('position_count', 0)}个。"
            })
        
        if 'holdings' in data:
            sections.append({
                'title': '持仓明细',
                'type': 'table',
                'content': data['holdings'][:10]  # 显示前10个持仓
            })
        
        return sections
    
    def _generate_risk_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成风险评估内容"""
        sections = []
        
        if 'error' in data:
            sections.append({
                'title': '错误信息',
                'type': 'error',
                'content': data['error']
            })
            return sections
        
        if 'risk_metrics' in data:
            metrics = data['risk_metrics']
            sections.append({
                'title': '风险指标',
                'type': 'summary',
                'content': f"组合总价值: {metrics.get('total_value', 0):,.2f}，"
                          f"集中度风险: {metrics.get('concentration_risk', 0):.2f}%，"
                          f"活跃预警: {metrics.get('active_alerts', 0)}个。"
            })
        
        if 'risk_alerts' in data and data['risk_alerts']:
            sections.append({
                'title': '风险预警',
                'type': 'alerts',
                'content': data['risk_alerts']
            })
        
        return sections
    
    def _generate_signal_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成信号分析内容"""
        sections = []
        
        if 'signal_summary' in data:
            summary = data['signal_summary']
            sections.append({
                'title': '信号概览',
                'type': 'summary',
                'content': f"分析期间({summary['analysis_period']})共生成{summary['total_signals']}个交易信号。"
            })
            
            if 'signal_types' in summary:
                sections.append({
                    'title': '信号类型分布',
                    'type': 'chart',
                    'content': summary['signal_types']
                })
        
        if 'recent_signals' in data:
            sections.append({
                'title': '最新信号',
                'type': 'table',
                'content': data['recent_signals']
            })
        
        return sections
    
    def _generate_market_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成市场概览内容"""
        sections = []
        
        if 'market_overview' in data:
            overview = data['market_overview']
            sections.append({
                'title': '市场概览',
                'type': 'summary',
                'content': f"今日活跃股票{overview['active_stocks']}只，"
                          f"总成交量{overview.get('total_volume', 0):,.0f}，"
                          f"平均数据点{overview.get('avg_data_points', 0):.1f}个。"
            })
        
        if 'stock_activity' in data:
            sections.append({
                'title': '活跃股票',
                'type': 'table',
                'content': data['stock_activity']
            })
        
        return sections
    
    def get_reports(self, report_type: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """获取报告列表"""
        try:
            if report_type:
                reports = RealtimeReport.get_reports_by_type(report_type, limit)
            else:
                reports = RealtimeReport.query.order_by(
                    RealtimeReport.generated_at.desc()
                ).limit(limit).all()
            
            return {
                'success': True,
                'data': [report.to_dict() for report in reports],
                'message': f'获取到 {len(reports)} 个报告'
            }
            
        except Exception as e:
            logger.error(f"获取报告列表失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取报告列表失败: {str(e)}'
            }
    
    def get_report_by_id(self, report_id: int) -> Dict[str, Any]:
        """根据ID获取报告"""
        try:
            report = RealtimeReport.query.get(report_id)
            
            if not report:
                return {
                    'success': False,
                    'message': '报告不存在'
                }
            
            return {
                'success': True,
                'data': report.to_dict(),
                'message': '报告获取成功'
            }
            
        except Exception as e:
            logger.error(f"获取报告失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取报告失败: {str(e)}'
            }
    
    def get_report_templates(self, template_type: Optional[str] = None) -> Dict[str, Any]:
        """获取报告模板"""
        try:
            if template_type:
                templates = ReportTemplate.get_templates_by_type(template_type)
            else:
                templates = ReportTemplate.query.filter_by(is_active=True)\
                                              .order_by(ReportTemplate.created_at.desc()).all()
            
            return {
                'success': True,
                'data': [template.to_dict() for template in templates],
                'message': f'获取到 {len(templates)} 个模板'
            }
            
        except Exception as e:
            logger.error(f"获取报告模板失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取报告模板失败: {str(e)}'
            }
    
    def create_report_template(self, template_name: str, template_type: str,
                             description: Optional[str] = None, components: List = None,
                             created_by: str = 'user') -> Dict[str, Any]:
        """创建报告模板"""
        try:
            # 验证模板类型
            if template_type not in self.report_types:
                return {
                    'success': False,
                    'message': f'不支持的模板类型: {template_type}'
                }
            
            # 获取默认配置
            template_config = self.default_templates.get(template_type, {})
            
            # 创建模板
            template = ReportTemplate.create_template(
                template_name=template_name,
                template_type=template_type,
                description=description,
                template_config=template_config,
                components=components or template_config.get('sections', []),
                created_by=created_by
            )
            
            return {
                'success': True,
                'data': template.to_dict(),
                'message': '模板创建成功'
            }
            
        except Exception as e:
            logger.error(f"创建报告模板失败: {str(e)}")
            return {
                'success': False,
                'message': f'创建报告模板失败: {str(e)}'
            }
    
    def run_stress_test(self, portfolio_id: str, scenarios: List[Dict] = None) -> Dict[str, Any]:
        """运行投资组合压力测试"""
        try:
            # 获取组合持仓
            positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
            
            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }
            
            # 默认压力测试场景
            if not scenarios:
                scenarios = [
                    {'name': '市场下跌10%', 'market_shock': -0.10},
                    {'name': '市场下跌20%', 'market_shock': -0.20},
                    {'name': '市场下跌30%', 'market_shock': -0.30},
                    {'name': '波动率上升50%', 'volatility_shock': 0.50},
                    {'name': '相关性上升至0.9', 'correlation_shock': 0.90}
                ]
            
            # 计算原始组合价值
            original_value = sum(pos.market_value or 0 for pos in positions)
            
            stress_results = []
            
            for scenario in scenarios:
                scenario_result = {
                    'scenario_name': scenario['name'],
                    'original_value': original_value,
                    'stressed_value': 0,
                    'pnl_change': 0,
                    'pnl_percentage': 0
                }
                
                # 简化的压力测试计算
                if 'market_shock' in scenario:
                    shock = scenario['market_shock']
                    stressed_value = original_value * (1 + shock)
                    scenario_result['stressed_value'] = stressed_value
                    scenario_result['pnl_change'] = stressed_value - original_value
                    scenario_result['pnl_percentage'] = shock * 100
                elif 'volatility_shock' in scenario:
                    # 波动率冲击的简化处理
                    vol_shock = scenario['volatility_shock']
                    stressed_value = original_value * (1 - vol_shock * 0.1)  # 简化计算
                    scenario_result['stressed_value'] = stressed_value
                    scenario_result['pnl_change'] = stressed_value - original_value
                    scenario_result['pnl_percentage'] = (stressed_value - original_value) / original_value * 100
                
                stress_results.append(scenario_result)
            
            return {
                'success': True,
                'data': {
                    'portfolio_id': portfolio_id,
                    'test_date': datetime.utcnow().isoformat(),
                    'original_value': original_value,
                    'scenarios': stress_results,
                    'worst_case': min(stress_results, key=lambda x: x['pnl_percentage']),
                    'best_case': max(stress_results, key=lambda x: x['pnl_percentage'])
                },
                'message': f'压力测试完成，测试了 {len(scenarios)} 个场景'
            }
            
        except Exception as e:
            logger.error(f"压力测试失败: {str(e)}")
            return {
                'success': False,
                'message': f'压力测试失败: {str(e)}'
            } 