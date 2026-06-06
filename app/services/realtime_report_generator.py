"""
实时分析报告生成服务
提供多种类型的分析报告生成功能
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from app.models.realtime_report import ReportTemplate, RealtimeReport, ReportSubscription
from app.models.trading_signal import TradingSignal
from app.models.portfolio_position import PortfolioPosition
from app.models.risk_alert import RiskAlert
from app.services.data_reader import ParquetDataReader
from app.services.parquet_event_store import ParquetEventStore

logger = logging.getLogger(__name__)


class RealtimeReportGenerator:
    """实时分析报告生成器"""
    
    def __init__(self):
        """初始化报告生成器"""
        self.data_reader = ParquetDataReader()
        self.minute_reader = self.data_reader.get_minute_reader()
        self.event_store = ParquetEventStore()
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
            report.update_generation_result(
                report_content=report_content,
                report_data=report_data,
                status='completed',
                generation_time=generation_time,
            )

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
                report.update_generation_result(
                    status='failed',
                    error_message=str(e),
                )
            return {
                'success': False,
                'message': f'报告生成失败: {str(e)}'
            }
    
    def _get_or_create_template(self, report_type: str, template_id: Optional[int]) -> Optional[ReportTemplate]:
        """获取或创建模板"""
        if template_id:
            template = ReportTemplate.get_by_id(template_id)
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
            ReportTemplate.update_template_by_id(template.id, is_default=True)
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
                portfolio_id = parameters.get('portfolio_id')
                if not portfolio_id:
                    raise ValueError('portfolio_id is required for portfolio_analysis')
                data.update(self._collect_portfolio_data(portfolio_id))
            elif report_type == 'risk_assessment':
                portfolio_id = parameters.get('portfolio_id')
                if not portfolio_id:
                    raise ValueError('portfolio_id is required for risk_assessment')
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

        minute_df = self._load_minute_frame("5min", today, today)

        minute_data_count = int(len(minute_df))
        active_stocks = int(minute_df["ts_code"].dropna().astype(str).nunique()) if not minute_df.empty and "ts_code" in minute_df.columns else 0
        
        # 获取当天 5min 技术指标数量与信号数量
        day_start = datetime.combine(today, datetime.min.time())
        day_end = datetime.combine(today, datetime.max.time())
        indicator_count = self._count_indicators_in_range(day_start, day_end, period_type='5min')
        signal_count = self._count_signals_in_range(day_start, day_end, period_type='5min')
        
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
        """收集投资组合数据（Parquet 数据源）"""
        from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository
        repo = PortfolioRepository(ParquetStateStore())

        positions = repo.list_positions(portfolio_id, active_only=True)

        if not positions:
            return {
                'portfolio_id': portfolio_id,
                'error': '组合中没有持仓数据'
            }

        metrics = repo.calculate_metrics(portfolio_id)

        holdings_data = []
        for pos in positions:
            market_value = float(pos.get('market_value') or 0)
            total_mv = metrics.get('total_market_value', 0) or 0
            holdings_data.append({
                'ts_code': pos.get('ts_code'),
                'position_size': pos.get('position_size'),
                'market_value': market_value,
                'unrealized_pnl': pos.get('unrealized_pnl'),
                'weight': (market_value / total_mv * 100) if total_mv > 0 else 0,
                'sector': pos.get('sector') or '未分类'
            })

        return {
            'portfolio_id': portfolio_id,
            'metrics': metrics,
            'holdings': holdings_data,
            'position_count': len(positions),
            'analysis_date': datetime.utcnow().isoformat()
        }
    
    def _collect_risk_data(self, portfolio_id: str) -> Dict[str, Any]:
        """收集风险数据（Parquet 数据源）"""
        from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository
        repo = PortfolioRepository(ParquetStateStore())

        positions = repo.list_positions(portfolio_id, active_only=True)

        if not positions:
            return {
                'portfolio_id': portfolio_id,
                'error': '组合中没有持仓数据'
            }

        # 获取风险预警
        try:
            alerts = RiskAlert.get_active_alerts()
            alert_list = [alert.to_dict() for alert in alerts[:10]]
            alert_count = len(alerts)
        except Exception:
            alert_list = []
            alert_count = 0

        # 计算基础风险指标
        total_value = sum(float(pos.get('market_value') or 0) for pos in positions)
        total_pnl = sum(float(pos.get('unrealized_pnl') or 0) for pos in positions)

        # 集中度风险
        market_values = [float(pos.get('market_value') or 0) for pos in positions]
        max_position = max(market_values) if market_values else 0
        concentration_risk = (max_position / total_value * 100) if total_value > 0 else 0

        # 行业分布
        sector_exposure = {}
        for pos in positions:
            sector = pos.get('sector') or '未分类'
            sector_exposure[sector] = sector_exposure.get(sector, 0) + float(pos.get('market_value') or 0)

        return {
            'portfolio_id': portfolio_id,
            'risk_metrics': {
                'total_value': total_value,
                'total_pnl': total_pnl,
                'concentration_risk': concentration_risk,
                'position_count': len(positions),
                'active_alerts': alert_count
            },
            'sector_exposure': sector_exposure,
            'risk_alerts': alert_list,
            'analysis_date': datetime.utcnow().isoformat()
        }
    
    def _collect_signal_data(self) -> Dict[str, Any]:
        """收集交易信号数据"""
        # 获取最近的交易信号
        recent_signals = self._load_recent_signals(
            start_time=datetime.utcnow() - timedelta(days=7),
            end_time=datetime.utcnow(),
            period_type='5min',
            limit=100,
        )
        
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
                'analysis_period': '最近7天',
                'period_type': '5min'
            },
            'recent_signals': [signal.to_dict() for signal in recent_signals[:20]],  # 最近20个信号
            'analysis_date': datetime.utcnow().isoformat()
        }

    def _count_indicators_in_range(self, start_time: datetime, end_time: datetime, period_type: Optional[str] = None) -> int:
        frame = self.event_store.get_indicators_by_time_range(
            ts_code=None,
            period_type=period_type,
            start_time=start_time,
            end_time=end_time,
        )
        return int(len(frame)) if not frame.empty else 0

    def _count_signals_in_range(self, start_time: datetime, end_time: datetime, period_type: Optional[str] = None) -> int:
        frame = self.event_store.get_signals_by_time_range(
            start_time=start_time,
            end_time=end_time,
        )
        if not frame.empty:
            if period_type and "period_type" in frame.columns:
                frame = frame[frame["period_type"] == period_type]
            return int(len(frame))
        return 0

    def _load_recent_signals(
        self,
        start_time: datetime,
        end_time: datetime,
        period_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Any]:
        frame = self.event_store.get_signals_by_time_range(start_time=start_time, end_time=end_time)
        if not frame.empty:
            if period_type and "period_type" in frame.columns:
                frame = frame[frame["period_type"] == period_type]
            frame = frame.sort_values("datetime", ascending=False).head(limit)
            return [TradingSignal._row_to_event(row) for _, row in frame.iterrows()]
        return []
    
    def _collect_market_data(self) -> Dict[str, Any]:
        """收集市场数据"""
        today = datetime.now().date()
        minute_df = self._load_minute_frame("5min", today, today)

        if minute_df.empty:
            active_stocks = []
        else:
            minute_df = minute_df.copy()
            minute_df["datetime"] = pd.to_datetime(minute_df["datetime"], errors="coerce")
            active_stocks = []
            for ts_code, group in minute_df.groupby("ts_code"):
                active_stocks.append(
                    {
                        "ts_code": ts_code,
                        "data_points": int(len(group)),
                        "high": float(group["close"].max()) if "close" in group.columns and not group["close"].empty else None,
                        "low": float(group["close"].min()) if "close" in group.columns and not group["close"].empty else None,
                        "total_volume": float(group["volume"].sum()) if "volume" in group.columns and not group["volume"].empty else 0,
                    }
                )

        total_volume = sum(stock["total_volume"] or 0 for stock in active_stocks)
        avg_data_points = np.mean([stock["data_points"] for stock in active_stocks]) if active_stocks else 0
        
        # 获取当天 5min 技术指标统计
        day_start = datetime.combine(today, datetime.min.time())
        day_end = datetime.combine(today, datetime.max.time())
        indicator_stats_df = self.event_store.get_indicators_by_time_range(
            ts_code=None,
            period_type='5min',
            start_time=day_start,
            end_time=day_end,
        )
        indicator_stats = {}
        if not indicator_stats_df.empty and "indicator_name" in indicator_stats_df.columns:
            indicator_stats = indicator_stats_df["indicator_name"].fillna("UNKNOWN").value_counts().to_dict()
        else:
            indicator_stats = {}
        
        return {
            'market_overview': {
                'active_stocks': len(active_stocks),
                'total_volume': total_volume,
                'avg_data_points': avg_data_points,
                'analysis_date': today.isoformat()
            },
            'stock_activity': active_stocks[:20],
            'indicator_distribution': indicator_stats
        }

    def _load_minute_frame(self, period_type: str, start_date, end_date) -> pd.DataFrame:
        """Load minute parquet data for a date range."""
        start_dt = datetime.combine(start_date, datetime.min.time()) if hasattr(start_date, "year") else start_date
        end_dt = datetime.combine(end_date, datetime.max.time()) if hasattr(end_date, "year") else end_date
        return self.minute_reader.get_data(period_type=period_type, start_time=start_dt, end_time=end_dt)
    
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
            md = data['market_data']
            sections.append({
                'title': '市场数据概览',
                'type': 'metrics',
                'content': [
                    {'label': '分钟数据点', 'value': md.get('minute_data_points', 0), 'format': 'number', 'icon': 'bi-graph-up', 'color': 'primary'},
                    {'label': '活跃股票', 'value': md.get('active_stocks', 0), 'format': 'number', 'icon': 'bi-bar-chart', 'color': 'success'},
                    {'label': '技术指标', 'value': md.get('technical_indicators', 0), 'format': 'number', 'icon': 'bi-speedometer2', 'color': 'info'},
                    {'label': '交易信号', 'value': md.get('trading_signals', 0), 'format': 'number', 'icon': 'bi-lightning', 'color': 'warning'},
                ]
            })

        if 'summary' in data:
            s = data['summary']
            sections.append({
                'title': '数据质量评估',
                'type': 'summary',
                'content': f"总活跃度: {s.get('total_activity', 0)}，数据覆盖: {s.get('data_coverage', '未知')}。数据接入正常，系统运行稳定。"
            })

        # 活跃度分析表格
        if 'market_data' in data:
            md = data['market_data']
            rows = [
                {'category': '分钟行情', 'count': md.get('minute_data_points', 0)},
                {'category': '技术指标', 'count': md.get('technical_indicators', 0)},
                {'category': '交易信号', 'count': md.get('trading_signals', 0)},
            ]
            sections.append({
                'title': '活跃度分析',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'category', 'label': '数据类别'},
                        {'key': 'count', 'label': '数量', 'format': 'number'},
                    ],
                    'rows': rows,
                }
            })

        return sections

    def _generate_portfolio_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成投资组合内容"""
        sections = []

        if 'error' in data:
            sections.append({'title': '错误信息', 'type': 'error', 'content': data['error']})
            return sections

        if 'metrics' in data:
            m = data['metrics']
            pnl = float(m.get('total_unrealized_pnl') or 0)
            sections.append({
                'title': '组合概览',
                'type': 'metrics',
                'content': [
                    {'label': '总市值', 'value': float(m.get('total_market_value') or 0), 'format': 'currency', 'icon': 'bi-wallet2', 'color': 'primary'},
                    {'label': '未实现盈亏', 'value': pnl, 'format': 'pnl', 'icon': 'bi-cash-stack', 'color': self._pnl_color(pnl)},
                    {'label': '持仓数量', 'value': data.get('position_count', 0), 'format': 'number', 'icon': 'bi-box-seam', 'color': 'info'},
                    {'label': '收益率', 'value': float(m.get('total_pnl_percentage') or 0), 'format': 'percent', 'icon': 'bi-percent', 'color': self._pnl_color(float(m.get('total_pnl_percentage') or 0))},
                ]
            })

        if 'holdings' in data and data['holdings']:
            sections.append({
                'title': '持仓明细',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'ts_code', 'label': '股票代码'},
                        {'key': 'position_size', 'label': '持仓数量', 'format': 'number'},
                        {'key': 'market_value', 'label': '市值', 'format': 'currency'},
                        {'key': 'unrealized_pnl', 'label': '浮动盈亏', 'format': 'pnl'},
                        {'key': 'weight', 'label': '权重%', 'format': 'percent'},
                        {'key': 'sector', 'label': '行业'},
                    ],
                    'rows': data['holdings'][:10],
                }
            })

        # 行业分布图表
        if 'metrics' in data:
            sector_dist = data['metrics'].get('sector_distribution') or {}
            if sector_dist:
                sections.append({
                    'title': '行业分布',
                    'type': 'chart',
                    'content': {
                        'chart_type': 'pie',
                        'data': [{'name': k, 'value': round(v, 1)} for k, v in sector_dist.items()],
                    }
                })

        # 权重排名
        if 'holdings' in data and data['holdings']:
            top = sorted(data['holdings'], key=lambda x: float(x.get('weight') or 0), reverse=True)[:5]
            sections.append({
                'title': '权重 TOP5',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'ts_code', 'label': '股票代码'},
                        {'key': 'market_value', 'label': '市值', 'format': 'currency'},
                        {'key': 'weight', 'label': '权重%', 'format': 'percent'},
                    ],
                    'rows': top,
                }
            })

        return sections

    def _generate_risk_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成风险评估内容"""
        sections = []

        if 'error' in data:
            sections.append({'title': '错误信息', 'type': 'error', 'content': data['error']})
            return sections

        if 'risk_metrics' in data:
            m = data['risk_metrics']
            pnl = float(m.get('total_pnl') or 0)
            conc = float(m.get('concentration_risk') or 0)
            alerts = int(m.get('active_alerts') or 0)
            sections.append({
                'title': '风险指标',
                'type': 'metrics',
                'content': [
                    {'label': '组合总价值', 'value': float(m.get('total_value') or 0), 'format': 'currency', 'icon': 'bi-shield-check', 'color': 'primary'},
                    {'label': '集中度风险', 'value': conc, 'format': 'percent', 'icon': 'bi-exclamation-diamond', 'color': self._risk_color(conc)},
                    {'label': '浮动盈亏', 'value': pnl, 'format': 'pnl', 'icon': 'bi-graph-up-arrow', 'color': self._pnl_color(pnl)},
                    {'label': '活跃预警', 'value': alerts, 'format': 'number', 'icon': 'bi-bell', 'color': 'danger' if alerts > 0 else 'success'},
                ]
            })

        if 'risk_alerts' in data and data['risk_alerts']:
            sections.append({
                'title': '风险预警',
                'type': 'alerts',
                'content': {
                    'severity_field': 'alert_level',
                    'items': data['risk_alerts'],
                }
            })

        # 行业敞口
        if 'sector_exposure' in data:
            se = data['sector_exposure']
            total_exposure = sum(float(v) for v in se.values()) or 1
            rows = [{'sector': k, 'exposure': v, 'weight_pct': v / total_exposure * 100} for k, v in se.items()]
            rows.sort(key=lambda x: x['exposure'], reverse=True)
            sections.append({
                'title': '行业敞口',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'sector', 'label': '行业'},
                        {'key': 'exposure', 'label': '敞口金额', 'format': 'currency'},
                        {'key': 'weight_pct', 'label': '占比%', 'format': 'percent'},
                    ],
                    'rows': rows,
                }
            })

        return sections

    def _generate_signal_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成信号分析内容"""
        sections = []

        if 'signal_summary' in data:
            s = data['signal_summary']
            total = s.get('total_signals', 0)
            types = s.get('signal_types', {})
            buy_count = types.get('BUY', 0)
            sell_count = types.get('SELL', 0)
            sections.append({
                'title': '信号概览',
                'type': 'metrics',
                'content': [
                    {'label': '总信号数', 'value': total, 'format': 'number', 'icon': 'bi-lightning', 'color': 'primary'},
                    {'label': '买入信号', 'value': buy_count, 'format': 'number', 'icon': 'bi-arrow-up-circle', 'color': 'success'},
                    {'label': '卖出信号', 'value': sell_count, 'format': 'number', 'icon': 'bi-arrow-down-circle', 'color': 'danger'},
                    {'label': '分析周期', 'value': s.get('analysis_period', '-'), 'format': 'text', 'icon': 'bi-clock', 'color': 'info'},
                ]
            })

            # 信号类型分布图表
            if types:
                sections.append({
                    'title': '信号类型分布',
                    'type': 'chart',
                    'content': {
                        'chart_type': 'bar',
                        'data': [{'name': k, 'value': v} for k, v in types.items()],
                    }
                })

        # 策略表现表格
        if 'signal_summary' in data:
            perf = data['signal_summary'].get('strategy_performance') or {}
            if perf:
                rows = [
                    {'strategy': k, 'count': v.get('count', 0), 'avg_strength': round(v.get('avg_strength', 0), 3)}
                    for k, v in perf.items()
                ]
                rows.sort(key=lambda x: x['count'], reverse=True)
                sections.append({
                    'title': '策略表现',
                    'type': 'table',
                    'content': {
                        'columns': [
                            {'key': 'strategy', 'label': '策略'},
                            {'key': 'count', 'label': '信号数', 'format': 'number'},
                            {'key': 'avg_strength', 'label': '平均强度', 'format': 'number'},
                        ],
                        'rows': rows,
                    }
                })

        # 最新信号表格
        if 'recent_signals' in data and data['recent_signals']:
            rows = data['recent_signals'][:15]
            sections.append({
                'title': '最新信号',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'ts_code', 'label': '股票代码'},
                        {'key': 'strategy_name', 'label': '策略'},
                        {'key': 'signal_type', 'label': '信号类型'},
                        {'key': 'signal_strength', 'label': '强度', 'format': 'number'},
                        {'key': 'confidence', 'label': '置信度', 'format': 'percent'},
                    ],
                    'rows': rows,
                }
            })

        return sections

    def _generate_market_content(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成市场概览内容"""
        sections = []

        if 'market_overview' in data:
            o = data['market_overview']
            sections.append({
                'title': '市场概览',
                'type': 'metrics',
                'content': [
                    {'label': '活跃股票', 'value': o.get('active_stocks', 0), 'format': 'number', 'icon': 'bi-graph-up', 'color': 'primary'},
                    {'label': '总成交量', 'value': float(o.get('total_volume') or 0), 'format': 'number', 'icon': 'bi-bar-chart', 'color': 'success'},
                    {'label': '平均数据点', 'value': float(o.get('avg_data_points') or 0), 'format': 'number', 'icon': 'bi-speedometer2', 'color': 'info'},
                    {'label': '分析日期', 'value': o.get('analysis_date', '-'), 'format': 'text', 'icon': 'bi-calendar', 'color': 'secondary'},
                ]
            })

        # 活跃股票表格
        if 'stock_activity' in data and data['stock_activity']:
            sections.append({
                'title': '活跃股票',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'ts_code', 'label': '股票代码'},
                        {'key': 'data_points', 'label': '数据点', 'format': 'number'},
                        {'key': 'high', 'label': '最高价', 'format': 'currency'},
                        {'key': 'low', 'label': '最低价', 'format': 'currency'},
                        {'key': 'total_volume', 'label': '总成交量', 'format': 'number'},
                    ],
                    'rows': data['stock_activity'][:15],
                }
            })

        # 指标分布图表
        if 'indicator_distribution' in data:
            dist = data['indicator_distribution']
            if dist:
                sections.append({
                    'title': '指标分布',
                    'type': 'chart',
                    'content': {
                        'chart_type': 'pie',
                        'data': [{'name': str(k), 'value': int(v)} for k, v in dist.items()],
                    }
                })

        # 成交排行
        if 'stock_activity' in data and data['stock_activity']:
            top = sorted(data['stock_activity'], key=lambda x: float(x.get('total_volume') or 0), reverse=True)[:10]
            sections.append({
                'title': '成交排行 TOP10',
                'type': 'table',
                'content': {
                    'columns': [
                        {'key': 'ts_code', 'label': '股票代码'},
                        {'key': 'total_volume', 'label': '总成交量', 'format': 'number'},
                        {'key': 'high', 'label': '最高价', 'format': 'currency'},
                        {'key': 'low', 'label': '最低价', 'format': 'currency'},
                    ],
                    'rows': top,
                }
            })

        return sections

    @staticmethod
    def _pnl_color(value: float) -> str:
        if value > 0:
            return 'success'
        if value < 0:
            return 'danger'
        return 'secondary'

    @staticmethod
    def _risk_color(pct: float, medium: float = 20.0, high: float = 40.0) -> str:
        if pct >= high:
            return 'danger'
        if pct >= medium:
            return 'warning'
        return 'success'
    
    def get_reports(self, report_type: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """获取报告列表"""
        try:
            if report_type:
                reports = RealtimeReport.get_reports_by_type(report_type, limit)
            else:
                reports = RealtimeReport.list_reports(limit=limit)
            
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
            report = RealtimeReport.get_by_id(report_id)
            
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
                templates = ReportTemplate.list_templates(active_only=True)
            
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
