import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from loguru import logger
import cvxpy as cp
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from app.extensions import db
from app.models import StockDailyHistory, FactorValues


class PortfolioOptimizer:
    """组合优化器"""
    UNSUPPORTED_CONSTRAINT_KEYS = set()
    
    def __init__(self):
        self.optimization_methods = {
            'mean_variance': self._mean_variance_optimization,
            'risk_parity': self._risk_parity_optimization,
            'equal_weight': self._equal_weight_optimization,
            'factor_neutral': self._factor_neutral_optimization,
            'black_litterman': self._black_litterman_optimization,
        }
    
    def optimize_portfolio(self, expected_returns: pd.Series, 
                          risk_model: pd.DataFrame = None,
                          method: str = 'mean_variance',
                          constraints: Dict[str, Any] = None) -> Dict[str, Any]:
        """优化投资组合"""
        try:
            if expected_returns.empty:
                return {'error': '预期收益率数据为空'}

            constraints = constraints or {}
            unsupported_constraints = sorted(
                key for key in constraints.keys() if key in self.UNSUPPORTED_CONSTRAINT_KEYS
            )
            if unsupported_constraints:
                return {
                    'error': f"不支持的约束条件: {', '.join(unsupported_constraints)}"
                }

            if method == 'factor_neutral':
                exposure_matrix = self._build_factor_exposure_matrix(
                    expected_returns.index.tolist(),
                    constraints.get('factor_exposures')
                )
                if exposure_matrix is None or exposure_matrix.empty:
                    return {
                        'error': 'factor_neutral优化需要有效的factor_exposures约束'
                    }
            
            # 获取风险模型
            if risk_model is None:
                risk_model = self._estimate_risk_model(expected_returns.index.tolist())
            
            # 检查优化方法
            if method not in self.optimization_methods:
                return {'error': f'不支持的优化方法: {method}'}
            
            # 执行优化
            optimization_func = self.optimization_methods[method]
            weights = optimization_func(expected_returns, risk_model, constraints)
            
            if weights is None or weights.empty:
                return {'error': '优化失败'}
            
            # 应用约束条件
            if constraints:
                weights = self._apply_constraints(weights, constraints)
            
            # 计算组合统计
            portfolio_stats = self._calculate_portfolio_stats(weights, expected_returns, risk_model)
            
            result = {
                'success': True,
                'method': method,
                'weights': weights.to_dict(),
                'portfolio_stats': portfolio_stats,
                'total_stocks': int(len(weights)),
                'non_zero_weights': int((weights > 0.001).sum())
            }
            
            logger.info(f"组合优化完成: {method}, {len(weights)} 只股票")
            return result
            
        except Exception as e:
            logger.error(f"组合优化失败: {method}, 错误: {e}")
            return {'error': str(e)}
    
    def _mean_variance_optimization(self, expected_returns: pd.Series, 
                                   risk_model: pd.DataFrame,
                                   constraints: Dict[str, Any] = None) -> pd.Series:
        """均值-方差优化"""
        try:
            n = len(expected_returns)
            
            # 风险厌恶系数
            risk_aversion = constraints.get('risk_aversion', 1.0) if constraints else 1.0
            
            # 定义优化变量
            w = cp.Variable(n)
            
            # 目标函数：最大化 expected_return - 0.5 * risk_aversion * variance
            portfolio_return = expected_returns.values @ w
            portfolio_variance = cp.quad_form(w, risk_model.values)
            objective = cp.Maximize(portfolio_return - 0.5 * risk_aversion * portfolio_variance)
            
            # 约束条件
            constraints_list = [
                cp.sum(w) == 1,  # 权重和为1
                w >= 0  # 不允许做空
            ]
            
            # 添加额外约束
            if constraints:
                # 最大权重约束
                if 'max_weight' in constraints:
                    max_weight = constraints['max_weight']
                    constraints_list.append(w <= max_weight)
                
                # 最小权重约束
                if 'min_weight' in constraints:
                    min_weight = constraints['min_weight']
                    constraints_list.append(w >= min_weight)
                
                # 最大集中度约束
                if 'max_concentration' in constraints:
                    max_conc = constraints['max_concentration']
                    constraints_list.append(cp.norm(w, 'inf') <= max_conc)
            
            # 求解优化问题
            problem = cp.Problem(objective, constraints_list)
            problem.solve(solver=cp.ECOS)
            
            if problem.status not in ["infeasible", "unbounded"]:
                weights = pd.Series(w.value, index=expected_returns.index)
                # 清理极小的权重
                weights[weights < 1e-6] = 0
                # 重新归一化
                weights = weights / weights.sum()
                return weights
            else:
                logger.warning(f"均值-方差优化失败: {problem.status}")
                return None
                
        except Exception as e:
            logger.error(f"均值-方差优化失败: {e}")
            return None
    
    def _risk_parity_optimization(self, expected_returns: pd.Series, 
                                 risk_model: pd.DataFrame,
                                 constraints: Dict[str, Any] = None) -> pd.Series:
        """风险平价优化"""
        try:
            n = len(expected_returns)
            
            def risk_parity_objective(weights):
                """风险平价目标函数"""
                weights = np.array(weights)
                portfolio_var = np.dot(weights, np.dot(risk_model.values, weights))
                
                # 计算边际风险贡献
                marginal_contrib = np.dot(risk_model.values, weights)
                risk_contrib = weights * marginal_contrib
                
                # 目标：最小化风险贡献的方差
                target_contrib = portfolio_var / n  # 等风险贡献
                return np.sum((risk_contrib - target_contrib) ** 2)
            
            # 约束条件
            constraints_list = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}  # 权重和为1
            ]
            
            # 边界条件
            bounds = [(0, 1) for _ in range(n)]  # 权重在0-1之间
            
            # 初始权重
            x0 = np.ones(n) / n
            
            # 求解
            result = minimize(
                risk_parity_objective,
                x0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints_list,
                options={'maxiter': 1000}
            )
            
            if result.success:
                weights = pd.Series(result.x, index=expected_returns.index)
                # 清理极小的权重
                weights[weights < 1e-6] = 0
                # 重新归一化
                weights = weights / weights.sum()
                return weights
            else:
                logger.warning(f"风险平价优化失败: {result.message}")
                return None
                
        except Exception as e:
            logger.error(f"风险平价优化失败: {e}")
            return None
    
    def _equal_weight_optimization(self, expected_returns: pd.Series, 
                                  risk_model: pd.DataFrame,
                                  constraints: Dict[str, Any] = None) -> pd.Series:
        """等权重优化"""
        try:
            n = len(expected_returns)
            weights = pd.Series(1.0 / n, index=expected_returns.index)
            return weights
            
        except Exception as e:
            logger.error(f"等权重优化失败: {e}")
            return None
    
    def _factor_neutral_optimization(self, expected_returns: pd.Series, 
                                    risk_model: pd.DataFrame,
                                    constraints: Dict[str, Any] = None) -> pd.Series:
        """因子中性优化"""
        try:
            constraints = constraints or {}
            factor_exposures = constraints.get('factor_exposures')
            exposure_matrix = self._build_factor_exposure_matrix(expected_returns.index.tolist(), factor_exposures)
            if exposure_matrix is None or exposure_matrix.empty:
                raise ValueError("factor_neutral优化需要有效的factor_exposures约束")

            aligned_risk = risk_model.reindex(
                index=expected_returns.index,
                columns=expected_returns.index,
                fill_value=0
            )

            mu = expected_returns.values
            cov = aligned_risk.values
            exposure_values = exposure_matrix.values

            risk_aversion = float(constraints.get('risk_aversion', 1.0))
            tolerance = float(constraints.get('exposure_tolerance', 1e-3))
            min_weight = float(constraints.get('min_weight', 0.0))
            max_weight = float(constraints.get('max_weight', 1.0))

            bounds = [(min_weight, max_weight) for _ in range(len(expected_returns))]

            def objective(weights):
                portfolio_return = np.dot(mu, weights)
                portfolio_variance = np.dot(weights, np.dot(cov, weights))
                return -(portfolio_return - 0.5 * risk_aversion * portfolio_variance)

            constraints_list = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
            ]

            for idx in range(exposure_values.shape[1]):
                factor_vec = exposure_values[:, idx]
                constraints_list.append({
                    'type': 'ineq',
                    'fun': lambda w, v=factor_vec, t=tolerance: t - np.dot(v, w)
                })
                constraints_list.append({
                    'type': 'ineq',
                    'fun': lambda w, v=factor_vec, t=tolerance: t + np.dot(v, w)
                })

            x0 = np.ones(len(expected_returns)) / len(expected_returns)
            result = minimize(
                objective,
                x0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints_list,
                options={'maxiter': 1000}
            )

            if not result.success:
                logger.warning(f"因子中性优化失败: {result.message}")
                return None

            weights = pd.Series(result.x, index=expected_returns.index)
            weights[weights < 1e-8] = 0
            if weights.sum() <= 0:
                return None
            return weights / weights.sum()
            
        except Exception as e:
            logger.error(f"因子中性优化失败: {e}")
            return None

    def _black_litterman_optimization(
        self,
        expected_returns: pd.Series,
        risk_model: pd.DataFrame,
        constraints: Dict[str, Any] = None,
    ) -> pd.Series:
        """简化版 Black-Litterman 优化。

        当前阶段仅提供研究型可用实现：
        - 使用 tau 对协方差做缩放
        - 若给定 views / view_confidences，则做线性混合
        - 最终沿用均值方差求权重
        """
        try:
            constraints = constraints or {}
            tau = float(constraints.get("tau", 0.05))
            scaled_risk = risk_model * max(tau, 1e-6)

            posterior_returns = expected_returns.copy().astype(float)
            views = constraints.get("views") or {}
            view_confidences = constraints.get("view_confidences") or {}

            for ts_code, view_return in views.items():
                if ts_code not in posterior_returns.index:
                    continue
                confidence = float(view_confidences.get(ts_code, 0.5))
                confidence = min(max(confidence, 0.0), 1.0)
                posterior_returns.loc[ts_code] = (
                    (1.0 - confidence) * posterior_returns.loc[ts_code]
                    + confidence * float(view_return)
                )

            blended_constraints = dict(constraints)
            blended_constraints.setdefault("risk_aversion", 1.0)
            if not hasattr(cp, "Variable"):
                return self._heuristic_weight_optimization(posterior_returns, blended_constraints)
            return self._mean_variance_optimization(posterior_returns, scaled_risk, blended_constraints)

        except Exception as e:
            logger.error(f"Black-Litterman优化失败: {e}")
            return None

    def _heuristic_weight_optimization(
        self,
        expected_returns: pd.Series,
        constraints: Dict[str, Any] = None,
    ) -> pd.Series:
        """在缺少求解器时提供研究型回退权重。"""
        try:
            constraints = constraints or {}
            shifted = expected_returns.astype(float) - float(expected_returns.min())
            base = shifted + 1e-6

            if float(base.sum()) <= 0:
                return self._equal_weight_optimization(expected_returns, None, constraints)

            weights = base / base.sum()
            return self._apply_constraints(weights, constraints)

        except Exception as e:
            logger.error(f"启发式权重优化失败: {e}")
            return None

    def _build_factor_exposure_matrix(self, ts_codes: List[str], factor_exposures: Any) -> Optional[pd.DataFrame]:
        """构建并对齐因子暴露矩阵（index=股票代码，columns=因子）。"""
        if factor_exposures is None:
            return None

        try:
            if isinstance(factor_exposures, pd.DataFrame):
                matrix = factor_exposures.copy()
            elif isinstance(factor_exposures, dict):
                matrix = pd.DataFrame(factor_exposures)
            else:
                return None

            # 支持两种方向：行是股票 或 列是股票
            if set(ts_codes).issubset(set(matrix.index)):
                aligned = matrix.reindex(index=ts_codes)
            elif set(ts_codes).issubset(set(matrix.columns)):
                aligned = matrix.T.reindex(index=ts_codes)
            else:
                return None

            aligned = aligned.apply(pd.to_numeric, errors='coerce').fillna(0.0)
            return aligned

        except Exception as e:
            logger.error(f"构建因子暴露矩阵失败: {e}")
            return None
    
    def _estimate_risk_model(self, ts_codes: List[str], 
                            lookback_days: int = 252) -> pd.DataFrame:
        """估计风险模型（协方差矩阵）"""
        try:
            # 获取历史价格数据
            end_date = datetime.now().date()
            start_date = end_date - pd.Timedelta(days=lookback_days + 50)
            
            price_query = StockDailyHistory.query.filter(
                StockDailyHistory.ts_code.in_(ts_codes),
                StockDailyHistory.trade_date >= start_date,
                StockDailyHistory.trade_date <= end_date
            ).order_by(StockDailyHistory.ts_code, StockDailyHistory.trade_date)
            
            price_data = pd.read_sql(price_query.statement, db.engine)
            
            if price_data.empty:
                # 如果没有数据，使用单位矩阵
                return pd.DataFrame(np.eye(len(ts_codes)), index=ts_codes, columns=ts_codes)
            
            # 透视表：日期为行，股票为列
            price_pivot = price_data.pivot_table(
                index='trade_date',
                columns='ts_code',
                values='close',
                aggfunc='first'
            )
            
            # 计算收益率
            returns = price_pivot.pct_change().dropna()
            
            # 只保留有足够数据的股票
            min_observations = min(60, len(returns) // 2)
            valid_stocks = returns.columns[returns.count() >= min_observations]
            returns = returns[valid_stocks]
            
            if returns.empty or len(returns.columns) < 2:
                # 如果数据不足，使用单位矩阵
                return pd.DataFrame(np.eye(len(ts_codes)), index=ts_codes, columns=ts_codes)
            
            # 使用Ledoit-Wolf收缩估计器
            lw = LedoitWolf()
            cov_matrix = lw.fit(returns.fillna(0)).covariance_
            
            # 转换为DataFrame
            risk_model = pd.DataFrame(cov_matrix, index=returns.columns, columns=returns.columns)
            
            # 确保包含所有股票（缺失的用0填充）
            for ts_code in ts_codes:
                if ts_code not in risk_model.index:
                    # 添加缺失股票，与其他股票协方差为0，方差为市场平均方差
                    avg_var = np.diag(risk_model).mean()
                    
                    # 扩展矩阵
                    new_row = pd.Series(0, index=risk_model.columns, name=ts_code)
                    new_col = pd.Series(0, index=list(risk_model.index) + [ts_code], name=ts_code)
                    new_col[ts_code] = avg_var
                    
                    risk_model = pd.concat([risk_model, new_row.to_frame().T])
                    risk_model[ts_code] = new_col
            
            # 重新排序以匹配输入顺序
            risk_model = risk_model.reindex(index=ts_codes, columns=ts_codes, fill_value=0)
            
            return risk_model
            
        except Exception as e:
            logger.error(f"估计风险模型失败: {e}")
            # 返回单位矩阵作为备选
            return pd.DataFrame(np.eye(len(ts_codes)), index=ts_codes, columns=ts_codes)
    
    def _apply_constraints(self, weights: pd.Series, constraints: Dict[str, Any]) -> pd.Series:
        """应用约束条件"""
        try:
            weights = weights.copy()
            
            # 最大权重约束
            if 'max_weight' in constraints:
                max_weight = constraints['max_weight']
                weights = weights.clip(upper=max_weight)
            
            # 最小权重约束
            if 'min_weight' in constraints:
                min_weight = constraints['min_weight']
                weights = weights.clip(lower=min_weight)
            
            # 个股集中度约束
            if 'max_concentration' in constraints:
                max_conc = constraints['max_concentration']
                if weights.max() > max_conc:
                    # 简单处理：将超过限制的权重设为最大值，重新分配剩余权重
                    excess_weight = weights[weights > max_conc].sum() - max_conc * (weights > max_conc).sum()
                    weights[weights > max_conc] = max_conc
                    
                    # 将多余权重分配给其他股票
                    other_stocks = weights[weights <= max_conc]
                    if len(other_stocks) > 0:
                        weights[weights <= max_conc] += excess_weight / len(other_stocks)

            industry_constraints = constraints.get('industry_constraints') or {}
            industry_map = constraints.get('industry_map') or {}
            if industry_constraints and industry_map:
                for industry, industry_rule in industry_constraints.items():
                    members = [code for code in weights.index if industry_map.get(code) == industry]
                    if not members:
                        continue
                    max_weight = float((industry_rule or {}).get('max_weight', 1.0))
                    industry_weight = float(weights.loc[members].sum())
                    if industry_weight <= max_weight:
                        continue

                    scale = max_weight / industry_weight if industry_weight > 0 else 1.0
                    weights.loc[members] = weights.loc[members] * scale

                    remaining_codes = [code for code in weights.index if code not in members]
                    remaining_weight = float(weights.loc[remaining_codes].sum()) if remaining_codes else 0.0
                    target_remaining = 1.0 - float(weights.loc[members].sum())
                    if remaining_codes and remaining_weight > 0 and target_remaining > 0:
                        weights.loc[remaining_codes] = weights.loc[remaining_codes] * (target_remaining / remaining_weight)
            
            # 重新归一化
            weights = weights / weights.sum()
            
            return weights
            
        except Exception as e:
            logger.error(f"应用约束条件失败: {e}")
            return weights
    
    def _calculate_portfolio_stats(self, weights: pd.Series, 
                                  expected_returns: pd.Series,
                                  risk_model: pd.DataFrame) -> Dict[str, float]:
        """计算组合统计指标"""
        try:
            # 确保索引一致
            common_index = weights.index.intersection(expected_returns.index)
            weights = weights[common_index]
            expected_returns = expected_returns[common_index]
            risk_model = risk_model.loc[common_index, common_index]
            
            # 组合预期收益率
            portfolio_return = np.dot(weights.values, expected_returns.values)
            
            # 组合风险（标准差）
            portfolio_variance = np.dot(weights.values, np.dot(risk_model.values, weights.values))
            portfolio_risk = np.sqrt(portfolio_variance)
            
            # 夏普比率（假设无风险利率为3%）
            risk_free_rate = 0.03 / 252  # 日化无风险利率
            sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_risk if portfolio_risk > 0 else 0
            
            # 权重集中度（HHI指数）
            concentration = np.sum(weights.values ** 2)
            
            # 有效股票数量
            effective_stocks = 1 / concentration
            
            stats = {
                'expected_return': float(portfolio_return),
                'expected_risk': float(portfolio_risk),
                'sharpe_ratio': float(sharpe_ratio),
                'concentration_hhi': float(concentration),
                'effective_stocks': float(effective_stocks),
                'max_weight': float(weights.max()),
                'min_weight': float(weights[weights > 0].min()) if (weights > 0).any() else 0.0,
                'turnover': 0.0  # 需要与前期权重比较计算
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"计算组合统计失败: {e}")
            return {}
    
    def calculate_turnover(self, new_weights: pd.Series, 
                          old_weights: pd.Series = None) -> float:
        """计算组合换手率"""
        try:
            if old_weights is None:
                return 1.0  # 如果没有前期权重，认为是全新组合
            
            # 确保索引一致
            all_stocks = new_weights.index.union(old_weights.index)
            new_weights = new_weights.reindex(all_stocks, fill_value=0)
            old_weights = old_weights.reindex(all_stocks, fill_value=0)
            
            # 换手率 = 0.5 * sum(|new_weight - old_weight|)
            turnover = 0.5 * np.sum(np.abs(new_weights.values - old_weights.values))
            
            return float(turnover)
            
        except Exception as e:
            logger.error(f"计算换手率失败: {e}")
            return 0.0
    
    def rebalance_portfolio(self, current_weights: pd.Series,
                           target_weights: pd.Series,
                           transaction_cost: float = 0.001) -> Dict[str, Any]:
        """组合再平衡"""
        try:
            # 计算交易指令
            all_stocks = current_weights.index.union(target_weights.index)
            current_weights = current_weights.reindex(all_stocks, fill_value=0)
            target_weights = target_weights.reindex(all_stocks, fill_value=0)
            
            trade_weights = target_weights - current_weights
            
            # 分离买入和卖出
            buy_weights = trade_weights[trade_weights > 0]
            sell_weights = trade_weights[trade_weights < 0]
            
            # 计算交易成本
            total_trade_value = np.sum(np.abs(trade_weights.values))
            total_cost = total_trade_value * transaction_cost
            
            # 计算换手率
            turnover = self.calculate_turnover(target_weights, current_weights)
            
            result = {
                'success': True,
                'trade_instructions': trade_weights[trade_weights != 0].to_dict(),
                'buy_list': buy_weights.to_dict(),
                'sell_list': sell_weights.to_dict(),
                'total_trade_value': float(total_trade_value),
                'transaction_cost': float(total_cost),
                'turnover': float(turnover),
                'net_exposure_change': float(target_weights.sum() - current_weights.sum())
            }
            
            return result
            
        except Exception as e:
            logger.error(f"组合再平衡失败: {e}")
            return {'error': str(e)} 
