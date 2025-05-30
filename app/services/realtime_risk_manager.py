"""
实时风险管理服务
提供实时风险计算、持仓风险监控、止损止盈管理和风险预警功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from sqlalchemy import func, desc, asc

from app.models.stock_minute_data import StockMinuteData
from app.models.stock_basic import StockBasic
from app.models.portfolio_position import PortfolioPosition
from app.models.risk_alert import RiskAlert
from app.extensions import db

logger = logging.getLogger(__name__)


class RealtimeRiskManager:
    """实时风险管理服务"""
    
    def __init__(self):
        self.confidence_levels = [0.95, 0.99]  # VaR置信水平
        self.risk_thresholds = {
            'position_weight': 0.20,  # 单一持仓权重阈值
            'sector_concentration': 0.30,  # 行业集中度阈值
            'var_limit': 0.05,  # VaR限制
            'volatility_limit': 0.30,  # 波动率限制
            'correlation_limit': 0.80,  # 相关性限制
            'drawdown_limit': 0.15  # 最大回撤限制
        }
    
    def calculate_portfolio_risk(self, portfolio_id: str, period_days: int = 252) -> Dict:
        """计算投资组合风险指标"""
        try:
            # 获取组合持仓
            positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
            
            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }
            
            # 获取股票代码列表
            stock_codes = [pos.ts_code for pos in positions]
            
            # 获取历史价格数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days + 30)  # 多取一些数据
            
            price_data = self._get_price_data(stock_codes, start_date, end_date)
            
            if price_data.empty:
                return {
                    'success': False,
                    'message': '无法获取价格数据'
                }
            
            # 计算收益率
            returns = price_data.pct_change().dropna()
            
            # 计算组合权重
            weights = self._get_portfolio_weights(positions)
            
            # 计算风险指标
            risk_metrics = self._calculate_risk_metrics(returns, weights, positions)
            
            # 计算VaR和CVaR
            var_metrics = self._calculate_var_cvar(returns, weights)
            
            # 计算相关性矩阵
            correlation_matrix = self._calculate_correlation_matrix(returns)
            
            # 计算Beta值
            beta_metrics = self._calculate_portfolio_beta(returns, weights)
            
            # 组合结果
            result = {
                'portfolio_id': portfolio_id,
                'calculation_date': datetime.now().isoformat(),
                'period_days': period_days,
                'total_positions': len(positions),
                'risk_metrics': risk_metrics,
                'var_metrics': var_metrics,
                'correlation_metrics': correlation_matrix,
                'beta_metrics': beta_metrics,
                'risk_alerts': self._check_risk_thresholds(portfolio_id, risk_metrics, var_metrics)
            }
            
            return {
                'success': True,
                'data': result,
                'message': f'成功计算组合 {portfolio_id} 的风险指标'
            }
            
        except Exception as e:
            logger.error(f"计算组合风险失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def monitor_position_risk(self, portfolio_id: str) -> Dict:
        """监控持仓风险"""
        try:
            positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
            
            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }
            
            risk_positions = []
            alerts = []
            
            for position in positions:
                # 更新当前价格
                current_price = self._get_current_price(position.ts_code)
                if current_price:
                    position.update_market_data(current_price)
                
                # 检查持仓风险
                position_risk = self._analyze_position_risk(position)
                risk_positions.append(position_risk)
                
                # 检查预警条件
                position_alerts = self._check_position_alerts(position)
                alerts.extend(position_alerts)
            
            # 计算组合级别风险
            portfolio_metrics = PortfolioPosition.calculate_portfolio_metrics(portfolio_id)
            
            return {
                'success': True,
                'data': {
                    'portfolio_id': portfolio_id,
                    'monitor_time': datetime.now().isoformat(),
                    'portfolio_metrics': portfolio_metrics,
                    'position_risks': risk_positions,
                    'active_alerts': alerts,
                    'risk_summary': self._summarize_portfolio_risk(risk_positions, alerts)
                },
                'message': f'成功监控组合 {portfolio_id} 的持仓风险'
            }
            
        except Exception as e:
            logger.error(f"监控持仓风险失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def manage_stop_loss_take_profit(self, portfolio_id: str, 
                                   stop_loss_method: str = 'percentage',
                                   stop_loss_value: float = 0.10,
                                   take_profit_method: str = 'percentage',
                                   take_profit_value: float = 0.20) -> Dict:
        """管理止损止盈"""
        try:
            positions = PortfolioPosition.get_portfolio_positions(portfolio_id)
            
            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }
            
            updated_positions = []
            triggered_orders = []
            
            for position in positions:
                # 计算止损止盈价格
                stop_loss_price = self._calculate_stop_loss_price(
                    position, stop_loss_method, stop_loss_value
                )
                take_profit_price = self._calculate_take_profit_price(
                    position, take_profit_method, take_profit_value
                )
                
                # 更新止损止盈价格
                position.stop_loss_price = stop_loss_price
                position.take_profit_price = take_profit_price
                
                # 检查是否触发
                if position.is_stop_loss_triggered():
                    triggered_orders.append({
                        'ts_code': position.ts_code,
                        'order_type': 'stop_loss',
                        'trigger_price': position.current_price,
                        'stop_loss_price': stop_loss_price,
                        'position_size': position.position_size,
                        'unrealized_pnl': position.unrealized_pnl
                    })
                
                if position.is_take_profit_triggered():
                    triggered_orders.append({
                        'ts_code': position.ts_code,
                        'order_type': 'take_profit',
                        'trigger_price': position.current_price,
                        'take_profit_price': take_profit_price,
                        'position_size': position.position_size,
                        'unrealized_pnl': position.unrealized_pnl
                    })
                
                updated_positions.append({
                    'ts_code': position.ts_code,
                    'current_price': position.current_price,
                    'avg_cost': position.avg_cost,
                    'stop_loss_price': stop_loss_price,
                    'take_profit_price': take_profit_price,
                    'stop_loss_distance': (position.current_price - stop_loss_price) / position.current_price * 100,
                    'take_profit_distance': (take_profit_price - position.current_price) / position.current_price * 100
                })
            
            # 提交数据库更改
            db.session.commit()
            
            return {
                'success': True,
                'data': {
                    'portfolio_id': portfolio_id,
                    'update_time': datetime.now().isoformat(),
                    'stop_loss_method': stop_loss_method,
                    'stop_loss_value': stop_loss_value,
                    'take_profit_method': take_profit_method,
                    'take_profit_value': take_profit_value,
                    'updated_positions': updated_positions,
                    'triggered_orders': triggered_orders,
                    'total_triggered': len(triggered_orders)
                },
                'message': f'成功更新组合 {portfolio_id} 的止损止盈设置'
            }
            
        except Exception as e:
            logger.error(f"管理止损止盈失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_risk_alerts(self, portfolio_id: str = None, 
                       alert_level: str = None, 
                       active_only: bool = True) -> Dict:
        """获取风险预警"""
        try:
            # 获取预警记录
            alerts = RiskAlert.get_active_alerts(
                alert_level=alert_level
            ) if active_only else RiskAlert.query.all()
            
            # 如果指定了组合ID，需要过滤相关股票
            if portfolio_id:
                position_codes = [pos.ts_code for pos in PortfolioPosition.get_portfolio_positions(portfolio_id)]
                alerts = [alert for alert in alerts if alert.ts_code in position_codes]
            
            # 按级别分组
            alerts_by_level = {
                'high': [],
                'medium': [],
                'low': []
            }
            
            for alert in alerts:
                level = alert.alert_level.lower()
                if level in alerts_by_level:
                    alerts_by_level[level].append(alert.to_dict())
            
            # 获取统计信息
            alert_stats = RiskAlert.get_alert_stats()
            
            return {
                'success': True,
                'data': {
                    'portfolio_id': portfolio_id,
                    'query_time': datetime.now().isoformat(),
                    'alerts_by_level': alerts_by_level,
                    'alert_stats': alert_stats,
                    'total_alerts': len(alerts),
                    'active_alerts': len([a for a in alerts if a.is_active])
                },
                'message': f'成功获取风险预警信息'
            }
            
        except Exception as e:
            logger.error(f"获取风险预警失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def create_risk_alert(self, ts_code: str, alert_type: str, 
                         alert_level: str, alert_message: str,
                         risk_value: float = None, threshold_value: float = None) -> Dict:
        """创建风险预警"""
        try:
            # 检查是否已存在相同的活跃预警
            existing_alert = RiskAlert.query.filter_by(
                ts_code=ts_code,
                alert_type=alert_type,
                is_active=True,
                is_resolved=False
            ).first()
            
            if existing_alert:
                return {
                    'success': False,
                    'message': f'股票 {ts_code} 已存在相同类型的活跃预警'
                }
            
            # 获取当前价格和持仓信息
            current_price = self._get_current_price(ts_code)
            position = PortfolioPosition.query.filter_by(
                ts_code=ts_code,
                is_active=True
            ).first()
            
            # 创建预警
            alert = RiskAlert.create_alert(
                ts_code=ts_code,
                alert_type=alert_type,
                alert_level=alert_level,
                alert_message=alert_message,
                risk_value=risk_value,
                threshold_value=threshold_value,
                current_price=current_price,
                position_size=position.position_size if position else None,
                portfolio_weight=position.weight if position else None
            )
            
            return {
                'success': True,
                'data': alert.to_dict(),
                'message': f'成功创建风险预警: {alert_message}'
            }
            
        except Exception as e:
            logger.error(f"创建风险预警失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _get_price_data(self, stock_codes: List[str], start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """获取价格数据"""
        try:
            # 查询分钟数据，聚合为日数据
            price_data = []
            
            for ts_code in stock_codes:
                data = StockMinuteData.query.filter(
                    StockMinuteData.ts_code == ts_code,
                    StockMinuteData.period_type == '60min',  # 使用小时数据
                    StockMinuteData.datetime >= start_date,
                    StockMinuteData.datetime <= end_date
                ).order_by(StockMinuteData.datetime).all()
                
                if data:
                    df = pd.DataFrame([{
                        'datetime': d.datetime,
                        'close': d.close,
                        'ts_code': d.ts_code
                    } for d in data])
                    
                    # 按日期聚合
                    df['date'] = df['datetime'].dt.date
                    daily_data = df.groupby('date')['close'].last().reset_index()
                    daily_data['ts_code'] = ts_code
                    price_data.append(daily_data)
            
            if price_data:
                # 合并所有股票数据
                all_data = pd.concat(price_data, ignore_index=True)
                # 透视表，日期为索引，股票为列
                pivot_data = all_data.pivot(index='date', columns='ts_code', values='close')
                return pivot_data.fillna(method='ffill')
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"获取价格数据失败: {str(e)}")
            return pd.DataFrame()
    
    def _get_portfolio_weights(self, positions: List[PortfolioPosition]) -> Dict[str, float]:
        """获取组合权重"""
        total_value = sum(pos.market_value or 0 for pos in positions)
        
        if total_value == 0:
            return {}
        
        return {
            pos.ts_code: (pos.market_value or 0) / total_value 
            for pos in positions
        }
    
    def _calculate_risk_metrics(self, returns: pd.DataFrame, weights: Dict, positions: List) -> Dict:
        """计算风险指标"""
        try:
            # 组合收益率
            portfolio_returns = pd.Series(0, index=returns.index)
            for ts_code, weight in weights.items():
                if ts_code in returns.columns:
                    portfolio_returns += returns[ts_code] * weight
            
            # 基础统计
            annual_return = portfolio_returns.mean() * 252
            annual_volatility = portfolio_returns.std() * np.sqrt(252)
            sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0
            
            # 最大回撤
            cumulative_returns = (1 + portfolio_returns).cumprod()
            rolling_max = cumulative_returns.expanding().max()
            drawdown = (cumulative_returns - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            # 行业集中度
            sector_concentration = self._calculate_sector_concentration(positions)
            
            # 持仓集中度
            position_concentration = max(weights.values()) if weights else 0
            
            return {
                'annual_return': annual_return,
                'annual_volatility': annual_volatility,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'sector_concentration': sector_concentration,
                'position_concentration': position_concentration,
                'tracking_error': portfolio_returns.std() * np.sqrt(252)
            }
            
        except Exception as e:
            logger.error(f"计算风险指标失败: {str(e)}")
            return {}
    
    def _calculate_var_cvar(self, returns: pd.DataFrame, weights: Dict) -> Dict:
        """计算VaR和CVaR"""
        try:
            # 组合收益率
            portfolio_returns = pd.Series(0, index=returns.index)
            for ts_code, weight in weights.items():
                if ts_code in returns.columns:
                    portfolio_returns += returns[ts_code] * weight
            
            var_metrics = {}
            
            for confidence in self.confidence_levels:
                # VaR计算
                var = np.percentile(portfolio_returns, (1 - confidence) * 100)
                
                # CVaR计算（条件VaR）
                cvar = portfolio_returns[portfolio_returns <= var].mean()
                
                var_metrics[f'var_{int(confidence*100)}'] = var
                var_metrics[f'cvar_{int(confidence*100)}'] = cvar
            
            return var_metrics
            
        except Exception as e:
            logger.error(f"计算VaR/CVaR失败: {str(e)}")
            return {}
    
    def _calculate_correlation_matrix(self, returns: pd.DataFrame) -> Dict:
        """计算相关性矩阵"""
        try:
            corr_matrix = returns.corr()
            
            # 计算平均相关性
            avg_correlation = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()
            
            # 找出高相关性股票对
            high_corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    corr_value = corr_matrix.iloc[i, j]
                    if abs(corr_value) > self.risk_thresholds['correlation_limit']:
                        high_corr_pairs.append({
                            'stock1': corr_matrix.columns[i],
                            'stock2': corr_matrix.columns[j],
                            'correlation': corr_value
                        })
            
            return {
                'average_correlation': avg_correlation,
                'max_correlation': corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].max(),
                'min_correlation': corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].min(),
                'high_correlation_pairs': high_corr_pairs,
                'correlation_matrix': corr_matrix.to_dict()
            }
            
        except Exception as e:
            logger.error(f"计算相关性矩阵失败: {str(e)}")
            return {}
    
    def _calculate_portfolio_beta(self, returns: pd.DataFrame, weights: Dict) -> Dict:
        """计算组合Beta值"""
        try:
            # 这里简化处理，实际应该使用市场指数数据
            # 假设市场收益率为所有股票的等权重组合
            market_returns = returns.mean(axis=1)
            
            # 组合收益率
            portfolio_returns = pd.Series(0, index=returns.index)
            for ts_code, weight in weights.items():
                if ts_code in returns.columns:
                    portfolio_returns += returns[ts_code] * weight
            
            # 计算Beta
            covariance = np.cov(portfolio_returns, market_returns)[0, 1]
            market_variance = np.var(market_returns)
            
            beta = covariance / market_variance if market_variance > 0 else 1.0
            
            return {
                'portfolio_beta': beta,
                'systematic_risk': beta * np.std(market_returns) * np.sqrt(252),
                'idiosyncratic_risk': np.sqrt(max(0, np.var(portfolio_returns) - beta**2 * market_variance)) * np.sqrt(252)
            }
            
        except Exception as e:
            logger.error(f"计算组合Beta失败: {str(e)}")
            return {'portfolio_beta': 1.0}
    
    def _calculate_sector_concentration(self, positions: List[PortfolioPosition]) -> float:
        """计算行业集中度"""
        try:
            sector_weights = {}
            total_weight = 0
            
            for pos in positions:
                sector = pos.sector or '未知'
                weight = pos.weight or 0
                
                if sector not in sector_weights:
                    sector_weights[sector] = 0
                sector_weights[sector] += weight
                total_weight += weight
            
            if total_weight == 0:
                return 0
            
            # 计算赫芬达尔指数
            hhi = sum((weight / total_weight) ** 2 for weight in sector_weights.values())
            
            return hhi
            
        except Exception as e:
            logger.error(f"计算行业集中度失败: {str(e)}")
            return 0
    
    def _get_current_price(self, ts_code: str) -> Optional[float]:
        """获取当前价格"""
        try:
            latest_data = StockMinuteData.query.filter_by(
                ts_code=ts_code
            ).order_by(desc(StockMinuteData.datetime)).first()
            
            return latest_data.close if latest_data else None
            
        except Exception as e:
            logger.error(f"获取 {ts_code} 当前价格失败: {str(e)}")
            return None
    
    def _analyze_position_risk(self, position: PortfolioPosition) -> Dict:
        """分析单个持仓风险"""
        try:
            # 计算基础指标
            pnl_percentage = position.calculate_pnl_percentage()
            
            # 风险评级
            risk_level = 'low'
            if abs(pnl_percentage) > 15:
                risk_level = 'high'
            elif abs(pnl_percentage) > 8:
                risk_level = 'medium'
            
            # 权重风险
            weight_risk = 'high' if (position.weight or 0) > self.risk_thresholds['position_weight'] * 100 else 'low'
            
            return {
                'ts_code': position.ts_code,
                'current_price': position.current_price,
                'avg_cost': position.avg_cost,
                'pnl_percentage': pnl_percentage,
                'weight': position.weight,
                'risk_level': risk_level,
                'weight_risk': weight_risk,
                'var_1d': position.var_1d,
                'var_5d': position.var_5d,
                'volatility': position.volatility,
                'beta': position.beta
            }
            
        except Exception as e:
            logger.error(f"分析持仓风险失败: {str(e)}")
            return {}
    
    def _check_position_alerts(self, position: PortfolioPosition) -> List[Dict]:
        """检查持仓预警"""
        alerts = []
        
        try:
            # 止损预警
            if position.is_stop_loss_triggered():
                alerts.append({
                    'ts_code': position.ts_code,
                    'alert_type': 'stop_loss_triggered',
                    'alert_level': 'high',
                    'message': f'{position.ts_code} 触发止损，当前价格 {position.current_price}，止损价格 {position.stop_loss_price}'
                })
            
            # 止盈预警
            if position.is_take_profit_triggered():
                alerts.append({
                    'ts_code': position.ts_code,
                    'alert_type': 'take_profit_triggered',
                    'alert_level': 'medium',
                    'message': f'{position.ts_code} 触发止盈，当前价格 {position.current_price}，止盈价格 {position.take_profit_price}'
                })
            
            # 权重过大预警
            if (position.weight or 0) > self.risk_thresholds['position_weight'] * 100:
                alerts.append({
                    'ts_code': position.ts_code,
                    'alert_type': 'position_concentration',
                    'alert_level': 'medium',
                    'message': f'{position.ts_code} 持仓权重过大: {position.weight:.1f}%'
                })
            
            # 大幅亏损预警
            pnl_pct = position.calculate_pnl_percentage()
            if pnl_pct < -15:
                alerts.append({
                    'ts_code': position.ts_code,
                    'alert_type': 'large_loss',
                    'alert_level': 'high',
                    'message': f'{position.ts_code} 大幅亏损: {pnl_pct:.1f}%'
                })
            
            return alerts
            
        except Exception as e:
            logger.error(f"检查持仓预警失败: {str(e)}")
            return []
    
    def _check_risk_thresholds(self, portfolio_id: str, risk_metrics: Dict, var_metrics: Dict) -> List[Dict]:
        """检查风险阈值"""
        alerts = []
        
        try:
            # 检查VaR限制
            for key, value in var_metrics.items():
                if 'var_' in key and abs(value) > self.risk_thresholds['var_limit']:
                    alerts.append({
                        'alert_type': 'var_limit_exceeded',
                        'alert_level': 'high',
                        'message': f'组合VaR超限: {key} = {value:.4f}'
                    })
            
            # 检查波动率限制
            if risk_metrics.get('annual_volatility', 0) > self.risk_thresholds['volatility_limit']:
                alerts.append({
                    'alert_type': 'volatility_limit_exceeded',
                    'alert_level': 'medium',
                    'message': f'组合波动率过高: {risk_metrics["annual_volatility"]:.4f}'
                })
            
            # 检查最大回撤
            if abs(risk_metrics.get('max_drawdown', 0)) > self.risk_thresholds['drawdown_limit']:
                alerts.append({
                    'alert_type': 'drawdown_limit_exceeded',
                    'alert_level': 'high',
                    'message': f'最大回撤过大: {risk_metrics["max_drawdown"]:.4f}'
                })
            
            # 检查行业集中度
            if risk_metrics.get('sector_concentration', 0) > self.risk_thresholds['sector_concentration']:
                alerts.append({
                    'alert_type': 'sector_concentration_high',
                    'alert_level': 'medium',
                    'message': f'行业集中度过高: {risk_metrics["sector_concentration"]:.4f}'
                })
            
            return alerts
            
        except Exception as e:
            logger.error(f"检查风险阈值失败: {str(e)}")
            return []
    
    def _calculate_stop_loss_price(self, position: PortfolioPosition, method: str, value: float) -> float:
        """计算止损价格"""
        try:
            if method == 'percentage':
                return position.avg_cost * (1 - value)
            elif method == 'atr':
                # 简化处理，实际应该计算ATR
                return position.current_price * (1 - value * 0.02)
            elif method == 'fixed':
                return position.avg_cost - value
            else:
                return position.avg_cost * 0.9  # 默认10%止损
                
        except Exception as e:
            logger.error(f"计算止损价格失败: {str(e)}")
            return position.avg_cost * 0.9
    
    def _calculate_take_profit_price(self, position: PortfolioPosition, method: str, value: float) -> float:
        """计算止盈价格"""
        try:
            if method == 'percentage':
                return position.avg_cost * (1 + value)
            elif method == 'atr':
                # 简化处理，实际应该计算ATR
                return position.current_price * (1 + value * 0.02)
            elif method == 'fixed':
                return position.avg_cost + value
            else:
                return position.avg_cost * 1.2  # 默认20%止盈
                
        except Exception as e:
            logger.error(f"计算止盈价格失败: {str(e)}")
            return position.avg_cost * 1.2
    
    def _summarize_portfolio_risk(self, position_risks: List[Dict], alerts: List[Dict]) -> Dict:
        """汇总组合风险"""
        try:
            high_risk_positions = len([p for p in position_risks if p.get('risk_level') == 'high'])
            medium_risk_positions = len([p for p in position_risks if p.get('risk_level') == 'medium'])
            
            high_alerts = len([a for a in alerts if a.get('alert_level') == 'high'])
            medium_alerts = len([a for a in alerts if a.get('alert_level') == 'medium'])
            
            # 整体风险评级
            overall_risk = 'low'
            if high_risk_positions > 0 or high_alerts > 0:
                overall_risk = 'high'
            elif medium_risk_positions > 2 or medium_alerts > 2:
                overall_risk = 'medium'
            
            return {
                'overall_risk_level': overall_risk,
                'high_risk_positions': high_risk_positions,
                'medium_risk_positions': medium_risk_positions,
                'total_alerts': len(alerts),
                'high_priority_alerts': high_alerts,
                'medium_priority_alerts': medium_alerts,
                'risk_score': high_risk_positions * 3 + medium_risk_positions * 2 + high_alerts * 2 + medium_alerts
            }
            
        except Exception as e:
            logger.error(f"汇总组合风险失败: {str(e)}")
            return {'overall_risk_level': 'unknown'} 