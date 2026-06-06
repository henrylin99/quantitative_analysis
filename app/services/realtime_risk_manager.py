"""
实时风险管理服务
提供实时风险计算、持仓风险监控、止损止盈管理和风险预警功能
数据源：Parquet（通过 PortfolioRepository）
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

from app.models.risk_alert import RiskAlert
from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

logger = logging.getLogger(__name__)

# ── Parquet 数据源（与 ml_factor_api 共享同一模式）──────────────
_state_store = ParquetStateStore()
_portfolio_repo = PortfolioRepository(_state_store)


# ── 辅助函数（替代 SQLite Model 实例方法，操作 dict）────────────

def _now_iso():
    return datetime.utcnow().isoformat()


def _calc_pnl_pct(pos: dict) -> float:
    avg_cost = float(pos.get('avg_cost') or 0)
    if avg_cost > 0:
        return (float(pos.get('current_price') or 0) - avg_cost) / avg_cost * 100
    return 0.0


def _is_sl_triggered(pos: dict) -> bool:
    sl = pos.get('stop_loss_price')
    cp = pos.get('current_price')
    return sl is not None and cp is not None and float(cp) <= float(sl)


def _is_tp_triggered(pos: dict) -> bool:
    tp = pos.get('take_profit_price')
    cp = pos.get('current_price')
    return tp is not None and cp is not None and float(cp) >= float(tp)


def _update_market_data_inplace(pos: dict, current_price: float) -> dict:
    """更新价格并计算市值/浮动盈亏（原地修改 dict）。"""
    pos['current_price'] = current_price
    pos['market_value'] = float(pos.get('position_size') or 0) * current_price
    pos['unrealized_pnl'] = (current_price - float(pos.get('avg_cost') or 0)) * float(pos.get('position_size') or 0)
    pos['updated_at'] = _now_iso()
    return pos


def _save_position(pos: dict) -> dict:
    """持久化持仓到 Parquet。"""
    return _portfolio_repo.upsert_position(pos)


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
        self.minute_reader = ParquetDataReader().get_minute_reader()

    # ── 公共方法 ──────────────────────────────────────────────────

    def calculate_portfolio_risk(self, portfolio_id: str, period_days: int = 252) -> Dict:
        """计算投资组合风险指标"""
        try:
            positions = _portfolio_repo.list_positions(portfolio_id)

            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }

            stock_codes = [pos.get('ts_code') for pos in positions]

            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days + 30)

            price_data = self._get_price_data(stock_codes, start_date, end_date)

            if price_data.empty:
                return {
                    'success': False,
                    'message': '无法获取价格数据'
                }

            returns = price_data.pct_change().dropna()
            weights = self._get_portfolio_weights(positions)

            risk_metrics = self._calculate_risk_metrics(returns, weights, positions)
            var_metrics = self._calculate_var_cvar(returns, weights)
            correlation_matrix = self._calculate_correlation_matrix(returns)
            beta_metrics = self._calculate_portfolio_beta(returns, weights)

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
            positions = _portfolio_repo.list_positions(portfolio_id)

            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }

            risk_positions = []
            alerts = []

            # 第一步：刷新实时价格
            for position in positions:
                current_price = self._get_current_price(position.get('ts_code', ''))
                if current_price:
                    _update_market_data_inplace(position, current_price)
                    _save_position(position)

            # 第二步：基于刷新后的市值计算实时权重
            total_value = sum(float(pos.get('market_value') or 0) for pos in positions)
            if total_value > 0:
                for pos in positions:
                    pos['weight'] = float(pos.get('market_value') or 0) / total_value * 100

            # 第三步：分析风险和预警
            for position in positions:
                position_risk = self._analyze_position_risk(position)
                risk_positions.append(position_risk)

                position_alerts = self._check_position_alerts(position)
                alerts.extend(position_alerts)

            # 计算组合级别风险
            portfolio_metrics = _portfolio_repo.calculate_metrics(portfolio_id)

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
            positions = _portfolio_repo.list_positions(portfolio_id)

            if not positions:
                return {
                    'success': False,
                    'message': '组合中没有持仓数据'
                }

            updated_positions = []
            triggered_orders = []

            for position in positions:
                stop_loss_price = self._calculate_stop_loss_price(
                    position, stop_loss_method, stop_loss_value
                )
                take_profit_price = self._calculate_take_profit_price(
                    position, take_profit_method, take_profit_value
                )

                # 更新止损止盈价格
                position['stop_loss_price'] = stop_loss_price
                position['take_profit_price'] = take_profit_price
                position['updated_at'] = _now_iso()
                _save_position(position)

                # 检查是否触发
                if _is_sl_triggered(position):
                    triggered_orders.append({
                        'ts_code': position.get('ts_code'),
                        'order_type': 'stop_loss',
                        'trigger_price': position.get('current_price'),
                        'stop_loss_price': stop_loss_price,
                        'position_size': position.get('position_size'),
                        'unrealized_pnl': position.get('unrealized_pnl')
                    })

                if _is_tp_triggered(position):
                    triggered_orders.append({
                        'ts_code': position.get('ts_code'),
                        'order_type': 'take_profit',
                        'trigger_price': position.get('current_price'),
                        'take_profit_price': take_profit_price,
                        'position_size': position.get('position_size'),
                        'unrealized_pnl': position.get('unrealized_pnl')
                    })

                current_price = float(position.get('current_price') or 0)
                updated_positions.append({
                    'ts_code': position.get('ts_code'),
                    'current_price': position.get('current_price'),
                    'avg_cost': position.get('avg_cost'),
                    'stop_loss_price': stop_loss_price,
                    'take_profit_price': take_profit_price,
                    'stop_loss_distance': (current_price - stop_loss_price) / current_price * 100 if current_price > 0 else 0,
                    'take_profit_distance': (take_profit_price - current_price) / current_price * 100 if current_price > 0 else 0
                })

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
            alerts = RiskAlert.get_active_alerts(
                alert_level=alert_level
            ) if active_only else RiskAlert.list_all()

            # 如果指定了组合ID，过滤相关股票
            if portfolio_id:
                position_codes = [pos.get('ts_code') for pos in _portfolio_repo.list_positions(portfolio_id)]
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

            alert_stats = RiskAlert.get_alert_stats()

            # active_alerts 返回列表（而非整数），前端需要遍历
            active_alert_list = [alert.to_dict() for alert in alerts if alert.is_active]

            return {
                'success': True,
                'data': {
                    'portfolio_id': portfolio_id,
                    'query_time': datetime.now().isoformat(),
                    'alerts_by_level': alerts_by_level,
                    'alert_stats': alert_stats,
                    'total_alerts': len(alerts),
                    'active_alerts': active_alert_list
                },
                'message': '成功获取风险预警信息'
            }

        except Exception as e:
            logger.error(f"获取风险预警失败: {str(e)}")
            return {'success': False, 'message': str(e)}

    def create_risk_alert(self, ts_code: str, alert_type: str,
                          alert_level: str, alert_message: str,
                          risk_value: float = None, threshold_value: float = None) -> Dict:
        """创建风险预警"""
        try:
            existing_alert = RiskAlert.get_existing_active_alert(ts_code, alert_type)

            if existing_alert:
                return {
                    'success': False,
                    'message': f'股票 {ts_code} 已存在相同类型的活跃预警'
                }

            current_price = self._get_current_price(ts_code)
            position = self._find_position_by_ts_code(ts_code)

            alert = RiskAlert.create_alert(
                ts_code=ts_code,
                alert_type=alert_type,
                alert_level=alert_level,
                alert_message=alert_message,
                risk_value=risk_value,
                threshold_value=threshold_value,
                current_price=current_price,
                position_size=position.get('position_size') if position else None,
                portfolio_weight=position.get('weight') if position else None
            )

            return {
                'success': True,
                'data': alert.to_dict(),
                'message': f'成功创建风险预警: {alert_message}'
            }

        except Exception as e:
            logger.error(f"创建风险预警失败: {str(e)}")
            return {'success': False, 'message': str(e)}

    # ── 私有辅助方法 ──────────────────────────────────────────────

    def _find_position_by_ts_code(self, ts_code: str) -> Optional[dict]:
        """在所有组合中查找指定股票的持仓。"""
        for pid in _portfolio_repo.list_portfolio_ids():
            for pos in _portfolio_repo.list_positions(pid, active_only=True):
                if pos.get('ts_code') == ts_code:
                    return pos
        return None

    def _get_price_data(self, stock_codes: List[str], start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """获取价格数据"""
        try:
            price_data = []

            for ts_code in stock_codes:
                data = self.minute_reader.get_data(
                    ts_code=ts_code,
                    period_type='5min',
                    start_time=start_date,
                    end_time=end_date,
                )
                if data.empty:
                    continue

                df = data.copy()
                df['datetime'] = pd.to_datetime(df['datetime'])
                df['date'] = df['datetime'].dt.date
                daily_data = df.sort_values('datetime').groupby('date')['close'].last().reset_index()
                daily_data['ts_code'] = ts_code
                price_data.append(daily_data)

            if price_data:
                all_data = pd.concat(price_data, ignore_index=True)
                pivot_data = all_data.pivot(index='date', columns='ts_code', values='close')
                return pivot_data.ffill()

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"获取价格数据失败: {str(e)}")
            return pd.DataFrame()

    def _get_portfolio_weights(self, positions: List[dict]) -> Dict[str, float]:
        """获取组合权重"""
        total_value = sum(float(pos.get('market_value') or 0) for pos in positions)

        if total_value == 0:
            return {}

        return {
            pos.get('ts_code', ''): float(pos.get('market_value') or 0) / total_value
            for pos in positions
        }

    def _calculate_risk_metrics(self, returns: pd.DataFrame, weights: Dict, positions: List[dict]) -> Dict:
        """计算风险指标"""
        try:
            portfolio_returns = pd.Series(0, index=returns.index)
            for ts_code, weight in weights.items():
                if ts_code in returns.columns:
                    portfolio_returns += returns[ts_code] * weight

            annual_return = portfolio_returns.mean() * 252
            annual_volatility = portfolio_returns.std() * np.sqrt(252)
            sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0

            cumulative_returns = (1 + portfolio_returns).cumprod()
            rolling_max = cumulative_returns.expanding().max()
            drawdown = (cumulative_returns - rolling_max) / rolling_max
            max_drawdown = drawdown.min()

            sector_concentration = self._calculate_sector_concentration(positions)
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
            portfolio_returns = pd.Series(0, index=returns.index)
            for ts_code, weight in weights.items():
                if ts_code in returns.columns:
                    portfolio_returns += returns[ts_code] * weight

            var_metrics = {}

            for confidence in self.confidence_levels:
                var = np.percentile(portfolio_returns, (1 - confidence) * 100)
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

            avg_correlation = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()

            high_corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i + 1, len(corr_matrix.columns)):
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
            market_returns = returns.mean(axis=1)

            portfolio_returns = pd.Series(0, index=returns.index)
            for ts_code, weight in weights.items():
                if ts_code in returns.columns:
                    portfolio_returns += returns[ts_code] * weight

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

    def _calculate_sector_concentration(self, positions: List[dict]) -> float:
        """计算行业集中度（赫芬达尔指数）"""
        try:
            sector_weights = {}
            total_weight = 0

            for pos in positions:
                sector = pos.get('sector') or '未知'
                weight = float(pos.get('weight') or 0)

                if sector not in sector_weights:
                    sector_weights[sector] = 0
                sector_weights[sector] += weight
                total_weight += weight

            if total_weight == 0:
                return 0

            hhi = sum((w / total_weight) ** 2 for w in sector_weights.values())
            return hhi

        except Exception as e:
            logger.error(f"计算行业集中度失败: {str(e)}")
            return 0

    def _get_current_price(self, ts_code: str) -> Optional[float]:
        """获取当前价格"""
        try:
            latest_data = self.minute_reader.get_latest_data(ts_code, '5min', 1)
            if latest_data.empty:
                return None
            return float(latest_data.iloc[0]['close'])

        except Exception as e:
            logger.error(f"获取 {ts_code} 当前价格失败: {str(e)}")
            return None

    def _analyze_position_risk(self, position: dict) -> Dict:
        """分析单个持仓风险"""
        try:
            pnl_percentage = _calc_pnl_pct(position)

            risk_level = 'low'
            if abs(pnl_percentage) > 15:
                risk_level = 'high'
            elif abs(pnl_percentage) > 8:
                risk_level = 'medium'

            weight = float(position.get('weight') or 0)
            weight_risk = 'high' if weight > self.risk_thresholds['position_weight'] * 100 else 'low'

            return {
                'ts_code': position.get('ts_code'),
                'current_price': position.get('current_price'),
                'avg_cost': position.get('avg_cost'),
                'pnl_percentage': pnl_percentage,
                'weight': weight,
                'risk_level': risk_level,
                'weight_risk': weight_risk,
                'var_1d': position.get('var_1d'),
                'var_5d': position.get('var_5d'),
                'volatility': position.get('volatility'),
                'beta': position.get('beta')
            }

        except Exception as e:
            logger.error(f"分析持仓风险失败: {str(e)}")
            return {}

    def _check_position_alerts(self, position: dict) -> List[Dict]:
        """检查持仓预警"""
        alerts = []

        try:
            if _is_sl_triggered(position):
                alerts.append({
                    'ts_code': position.get('ts_code'),
                    'alert_type': 'stop_loss_triggered',
                    'alert_level': 'high',
                    'message': f'{position.get("ts_code")} 触发止损，当前价格 {position.get("current_price")}，止损价格 {position.get("stop_loss_price")}'
                })

            if _is_tp_triggered(position):
                alerts.append({
                    'ts_code': position.get('ts_code'),
                    'alert_type': 'take_profit_triggered',
                    'alert_level': 'medium',
                    'message': f'{position.get("ts_code")} 触发止盈，当前价格 {position.get("current_price")}，止盈价格 {position.get("take_profit_price")}'
                })

            weight = float(position.get('weight') or 0)
            if weight > self.risk_thresholds['position_weight'] * 100:
                alerts.append({
                    'ts_code': position.get('ts_code'),
                    'alert_type': 'position_concentration',
                    'alert_level': 'medium',
                    'message': f'{position.get("ts_code")} 持仓权重过大: {weight:.1f}%'
                })

            pnl_pct = _calc_pnl_pct(position)
            if pnl_pct < -15:
                alerts.append({
                    'ts_code': position.get('ts_code'),
                    'alert_type': 'large_loss',
                    'alert_level': 'high',
                    'message': f'{position.get("ts_code")} 大幅亏损: {pnl_pct:.1f}%'
                })

            return alerts

        except Exception as e:
            logger.error(f"检查持仓预警失败: {str(e)}")
            return []

    def _check_risk_thresholds(self, portfolio_id: str, risk_metrics: Dict, var_metrics: Dict) -> List[Dict]:
        """检查风险阈值"""
        alerts = []

        try:
            for key, value in var_metrics.items():
                if 'var_' in key and abs(value) > self.risk_thresholds['var_limit']:
                    alerts.append({
                        'alert_type': 'var_limit_exceeded',
                        'alert_level': 'high',
                        'message': f'组合VaR超限: {key} = {value:.4f}'
                    })

            if risk_metrics.get('annual_volatility', 0) > self.risk_thresholds['volatility_limit']:
                alerts.append({
                    'alert_type': 'volatility_limit_exceeded',
                    'alert_level': 'medium',
                    'message': f'组合波动率过高: {risk_metrics["annual_volatility"]:.4f}'
                })

            if abs(risk_metrics.get('max_drawdown', 0)) > self.risk_thresholds['drawdown_limit']:
                alerts.append({
                    'alert_type': 'drawdown_limit_exceeded',
                    'alert_level': 'high',
                    'message': f'最大回撤过大: {risk_metrics["max_drawdown"]:.4f}'
                })

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

    def _calculate_stop_loss_price(self, position: dict, method: str, value: float) -> float:
        """计算止损价格"""
        try:
            avg_cost = float(position.get('avg_cost') or 0)
            current_price = float(position.get('current_price') or 0)
            if method == 'percentage':
                return avg_cost * (1 - value)
            elif method == 'atr':
                return current_price * (1 - value * 0.02)
            elif method == 'fixed':
                return avg_cost - value
            else:
                return avg_cost * 0.9
        except Exception as e:
            logger.error(f"计算止损价格失败: {str(e)}")
            return float(position.get('avg_cost') or 0) * 0.9

    def _calculate_take_profit_price(self, position: dict, method: str, value: float) -> float:
        """计算止盈价格"""
        try:
            avg_cost = float(position.get('avg_cost') or 0)
            current_price = float(position.get('current_price') or 0)
            if method == 'percentage':
                return avg_cost * (1 + value)
            elif method == 'atr':
                return current_price * (1 + value * 0.02)
            elif method == 'fixed':
                return avg_cost + value
            else:
                return avg_cost * 1.2
        except Exception as e:
            logger.error(f"计算止盈价格失败: {str(e)}")
            return float(position.get('avg_cost') or 0) * 1.2

    def _summarize_portfolio_risk(self, position_risks: List[Dict], alerts: List[Dict]) -> Dict:
        """汇总组合风险"""
        try:
            high_risk_positions = len([p for p in position_risks if p.get('risk_level') == 'high'])
            medium_risk_positions = len([p for p in position_risks if p.get('risk_level') == 'medium'])

            high_alerts = len([a for a in alerts if a.get('alert_level') == 'high'])
            medium_alerts = len([a for a in alerts if a.get('alert_level') == 'medium'])

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
