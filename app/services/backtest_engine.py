import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
from loguru import logger

from app.services.factor_engine import FactorEngine
from app.services.ml_models import MLModelManager
from app.services.stock_scoring import StockScoringEngine
from app.services.portfolio_optimizer import PortfolioOptimizer
from config import Config
from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import BacktestRepository, ParquetStateStore


class BacktestEngine:
    """回测验证引擎"""
    
    def __init__(self):
        self.factor_engine = None
        self.ml_manager = None
        self.scoring_engine = None
        self.portfolio_optimizer = None
        self.data_reader = ParquetDataReader()
        self.state_store = ParquetStateStore()
        self.backtest_repo = BacktestRepository(self.state_store)
    
    def _get_factor_engine(self):
        """延迟初始化因子引擎"""
        if self.factor_engine is None:
            self.factor_engine = FactorEngine()
        return self.factor_engine
    
    def _get_ml_manager(self):
        """延迟初始化ML管理器"""
        if self.ml_manager is None:
            self.ml_manager = MLModelManager()
        return self.ml_manager
    
    def _get_scoring_engine(self):
        """延迟初始化评分引擎"""
        if self.scoring_engine is None:
            self.scoring_engine = StockScoringEngine()
        return self.scoring_engine
    
    def _get_portfolio_optimizer(self):
        """延迟初始化投资组合优化器"""
        if self.portfolio_optimizer is None:
            self.portfolio_optimizer = PortfolioOptimizer()
        return self.portfolio_optimizer
        
    def run_backtest(self, strategy_config: Dict[str, Any], 
                    start_date: str, end_date: str,
                    initial_capital: float = 1000000.0,
                    rebalance_frequency: str = 'monthly') -> Dict[str, Any]:
        """
        运行回测
        
        Args:
            strategy_config: 策略配置
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            rebalance_frequency: 再平衡频率 ('daily', 'weekly', 'monthly')
            
        Returns:
            回测结果
        """
        try:
            logger.info(f"开始回测: {start_date} to {end_date}")
            backtest_run = self.backtest_repo.create_run(
                strategy_config=strategy_config,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                rebalance_frequency=rebalance_frequency,
            )
            
            # 生成交易日期
            trade_dates = self._generate_trade_dates(start_date, end_date, rebalance_frequency)
            # 完整交易日历，用于把信号日的调仓推迟到下一个交易日执行
            calendar_dates = self.data_reader.get_trade_dates(start_date, end_date)

            # 初始化回测状态
            executed_states = []  # 每次实际成交后的 (日期, 持仓, 现金)
            positions = {}
            cash = initial_capital
            total_value = initial_capital
            last_prices = {}

            # 记录每次调仓数据（逐日净值在循环结束后统一 mark-to-market）
            daily_positions = []
            daily_turnover = []

            for i, trade_date in enumerate(trade_dates):
                logger.info(f"处理交易日: {trade_date}")

                try:
                    # 获取当日选股结果（信号在 t 日收盘后产生）
                    selected_stocks = self._get_stock_selection(strategy_config, trade_date)

                    if not selected_stocks:
                        logger.warning(f"日期 {trade_date} 没有选出股票")
                        continue

                    # 组合优化（协方差只使用 trade_date 及之前的数据，避免前视偏差）
                    target_weights = self._get_target_weights(
                        selected_stocks, strategy_config.get('optimization', {}),
                        as_of_date=trade_date,
                    )

                    # t+1 执行：信号日收盘后才能观察到的信息，只能在下一个交易日成交
                    exec_date = self._next_trade_date(calendar_dates, trade_date)
                    if exec_date is None:
                        logger.info(f"信号日 {trade_date} 之后没有可执行的交易日，跳过")
                        continue

                    all_codes = list(set(list(positions.keys()) + list(target_weights.keys())))
                    exec_prices, tradability = self._get_execution_snapshot(exec_date, all_codes)

                    # 估值价格：当日无行情的持仓（停牌）沿用最近已知价格，而不是按 0 计
                    valuation_prices = dict(last_prices)
                    valuation_prices.update(exec_prices)
                    last_prices = valuation_prices
                    current_portfolio_value = self._calculate_portfolio_value(
                        positions, valuation_prices, cash
                    )

                    # 执行再平衡（停牌/涨跌停限制在内部处理）
                    new_positions, new_cash, turnover, _cost_breakdown = self._rebalance_portfolio(
                        positions, cash, target_weights, exec_prices, tradability,
                        current_portfolio_value,
                        commission_rate=float(strategy_config.get('commission_rate', 0.001)),
                        slippage_rate=float(strategy_config.get('slippage_rate', 0.0)),
                        stamp_duty_rate=float(strategy_config.get('stamp_duty_rate', Config.DEFAULT_STAMP_DUTY_RATE)),
                    )

                    # 更新状态：交易成本通过现金扣减体现，由逐日净值如实反映
                    positions = new_positions
                    cash = new_cash
                    executed_states.append({
                        'date': exec_date,
                        'positions': positions.copy(),
                        'cash': cash,
                    })

                    daily_positions.append(positions.copy())
                    daily_turnover.append(turnover)

                except Exception as e:
                    logger.error(f"处理交易日 {trade_date} 时出错: {e}")
                    continue

            # 逐日 mark-to-market 净值曲线：只在调仓日记净值点会系统性低估
            # 最大回撤、低估波动率并虚高夏普（月度调仓时一年只有 ~12 个观测点）
            portfolio_values = self._build_daily_nav(
                calendar_dates, executed_states, initial_capital
            )
            total_value = portfolio_values[-1]['total_value'] if portfolio_values else initial_capital

            # 逐日收益率
            daily_returns = []
            for prev, cur in zip(portfolio_values[:-1], portfolio_values[1:]):
                if prev['total_value'] > 0:
                    daily_returns.append(
                        (cur['total_value'] - prev['total_value']) / prev['total_value']
                    )

            # 获取基准收益
            benchmark_returns = self._get_benchmark_returns(
                start_date,
                end_date,
                benchmark_code=strategy_config.get('benchmark_index', '000300.SH'),
            )

            # 计算回测指标
            performance_metrics = self._calculate_performance_metrics(
                portfolio_values, daily_returns, start_date, end_date,
                benchmark_returns=benchmark_returns,
                initial_capital=initial_capital,
            )
            execution_assumptions = self._build_execution_assumptions(strategy_config)
            trade_constraints = self._build_trade_constraints(strategy_config)

            result = self._build_response_payload(
                strategy_config=strategy_config,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_value=total_value,
                portfolio_values=portfolio_values,
                daily_returns=daily_returns,
                daily_positions=daily_positions,
                daily_turnover=daily_turnover,
                performance_metrics=performance_metrics,
                benchmark_returns=benchmark_returns,
                final_prices=last_prices,
                run_id=backtest_run["id"],
                execution_assumptions=execution_assumptions,
                trade_constraints=trade_constraints,
            )
            self.backtest_repo.update_summary(int(backtest_run["id"]), {
                'final_value': total_value,
                'total_return': result.get('total_return'),
                'annual_return': performance_metrics.get('annualized_return'),
                'max_drawdown': performance_metrics.get('max_drawdown'),
            })
            return result
            
        except Exception as e:
            logger.error(f"回测失败: {e}")
            return {'error': str(e)}
    
    def _generate_trade_dates(self, start_date: str, end_date: str,
                            frequency: str) -> List[str]:
        """生成交易日期"""
        try:
            # 获取所有交易日
            all_dates = self.data_reader.get_trade_dates(start_date, end_date)
            
            if frequency == 'daily':
                return all_dates
            elif frequency == 'weekly':
                # 每周第一个交易日
                weekly_dates = []
                current_week = None
                for date in all_dates:
                    week = pd.to_datetime(date).isocalendar()[1]
                    if week != current_week:
                        weekly_dates.append(date)
                        current_week = week
                return weekly_dates
            elif frequency == 'monthly':
                # 每月第一个交易日
                monthly_dates = []
                current_month = None
                for date in all_dates:
                    month = pd.to_datetime(date).month
                    if month != current_month:
                        monthly_dates.append(date)
                        current_month = month
                return monthly_dates
            else:
                return all_dates
                
        except Exception as e:
            logger.error(f"生成交易日期失败: {e}")
            return []
    
    def _get_stock_selection(self, strategy_config: Dict[str, Any], 
                           trade_date: str) -> List[Dict[str, Any]]:
        """获取股票选择结果"""
        try:
            selection_method = strategy_config.get('selection_method', 'factor_based')
            top_n = strategy_config.get('top_n', 50)
            
            if selection_method == 'ml_based':
                model_ids = strategy_config.get('model_ids', [])
                if not model_ids:
                    return []
                
                return self._get_scoring_engine().ml_based_selection(
                    trade_date, model_ids, top_n, 'average'
                )
            else:
                factor_list = strategy_config.get('factor_list', [])
                if not factor_list:
                    return []
                
                factor_scores = self._get_scoring_engine().calculate_factor_scores(
                    trade_date, factor_list
                )
                
                if factor_scores.empty:
                    return []
                
                weights_config = strategy_config.get('weights', {})
                composite_scores = self._get_scoring_engine().calculate_composite_score(
                    factor_scores, weights_config, 'equal_weight'
                )
                
                return self._get_scoring_engine().rank_stocks(composite_scores, top_n)
                
        except Exception as e:
            logger.error(f"获取股票选择结果失败: {e}")
            return []
    
    # 截面 z-score → 年化预期收益的线性映射区间（保守量级，
    # 与年化协方差匹配；如需调整请同步评估 risk_aversion）
    EXPECTED_RETURN_LOWER = -0.15
    EXPECTED_RETURN_UPPER = 0.30

    def _scores_to_expected_returns(self, selected_stocks: List[Dict[str, Any]]) -> pd.Series:
        """把截面 z-score 映射为量纲合理的年化预期收益。

        composite_score 是 ±3 左右的 z-score，而优化器里的协方差是收益率
        方差（日频 ~1e-4，年化 ~1e-2）。直接把分数当预期收益喂给均值方差，
        目标函数的收益项会比风险项大三四个数量级，优化退化为把权重全部押给
        分数最高股票的角点解。这里保留截面排序信息，线性映射到保守的
        年化收益区间，与年化协方差量纲匹配。
        """
        scores = pd.Series({
            stock['ts_code']: stock.get('composite_score', stock.get('ensemble_score', 0))
            for stock in selected_stocks
        })
        pct_rank = scores.rank(pct=True)
        lower, upper = self.EXPECTED_RETURN_LOWER, self.EXPECTED_RETURN_UPPER
        return lower + (upper - lower) * pct_rank

    def _get_target_weights(self, selected_stocks: List[Dict[str, Any]], 
                          optimization_config: Dict[str, Any],
                          as_of_date: str = None) -> Dict[str, float]:
        """获取目标权重"""
        try:
            method = optimization_config.get('method', 'equal_weight')
            
            if method == 'equal_weight':
                # 等权重
                weight = 1.0 / len(selected_stocks)
                return {stock['ts_code']: weight for stock in selected_stocks}
            else:
                # 使用组合优化：协方差按调仓日截断估计（前视防护）+ 年化口径匹配
                expected_returns = self._scores_to_expected_returns(selected_stocks)
                
                result = self._get_portfolio_optimizer().optimize_portfolio(
                    expected_returns,
                    method=method,
                    constraints=optimization_config.get('constraints'),
                    as_of_date=as_of_date,
                    annualize_cov=True,
                )
                
                if 'error' in result:
                    # 如果优化失败，使用等权重
                    weight = 1.0 / len(selected_stocks)
                    return {stock['ts_code']: weight for stock in selected_stocks}
                
                return result['weights']
                
        except Exception as e:
            logger.error(f"获取目标权重失败: {e}")
            # 默认等权重
            weight = 1.0 / len(selected_stocks)
            return {stock['ts_code']: weight for stock in selected_stocks}

    def _build_daily_nav(self, calendar_dates: List[str],
                         executed_states: List[Dict[str, Any]],
                         initial_capital: float) -> List[Dict[str, Any]]:
        """逐日 mark-to-market 净值。

        - 现金只在调仓事件日变动
        - 持仓每个交易日按最近已知收盘价估值（停牌股沿用最后成交价）
        - 第一个调仓事件之前净值为初始资金（纯现金）
        """
        events = {state['date']: state for state in executed_states}
        all_codes = sorted({code for state in executed_states for code in state['positions']})

        close_pivot = pd.DataFrame()
        if all_codes and calendar_dates:
            try:
                px_df = self.data_reader.get_daily(
                    ts_codes=all_codes, start_date=calendar_dates[0], end_date=calendar_dates[-1]
                )
                if not px_df.empty:
                    close_pivot = px_df.pivot_table(
                        index='trade_date', columns='ts_code', values='close', aggfunc='first'
                    ).sort_index()
                    # 统一索引为 Timestamp，兼容未归一化日期的调用方
                    close_pivot.index = pd.to_datetime(close_pivot.index)
            except Exception as e:
                # 快速失败：行情缺失时持仓会按 0 估值，净值静默塌缩为纯现金，
                # 这种"看起来正常的假结果"比直接报错危害大得多
                raise RuntimeError(f"构建逐日净值读取行情失败: {e}") from e

        nav = []
        current_positions: Dict[str, int] = {}
        current_cash = float(initial_capital)
        last_prices: Dict[str, float] = {}

        for date_text in calendar_dates:
            event = events.get(date_text)
            if event is not None:
                current_positions = event['positions']
                current_cash = event['cash']

            key = pd.Timestamp(date_text)
            if not close_pivot.empty and key in close_pivot.index:
                row = close_pivot.loc[key]
                for code, price in row.items():
                    if pd.notna(price) and price > 0:
                        last_prices[code] = float(price)

            positions_value = sum(
                shares * last_prices.get(code, 0.0)
                for code, shares in current_positions.items()
            )
            nav.append({
                'date': date_text,
                'total_value': positions_value + current_cash,
                'cash': current_cash,
                'positions_value': positions_value,
            })
        return nav

    def _next_trade_date(self, calendar_dates: List[str], signal_date: str) -> Optional[str]:
        """返回严格晚于 signal_date 的第一个交易日"""
        for date in calendar_dates:
            if date > signal_date:
                return date
        return None

    def _get_stock_names(self, ts_codes: List[str]) -> Dict[str, str]:
        """获取股票名称（用于识别 ST 的 5% 涨跌停幅度）"""
        try:
            if not ts_codes:
                return {}
            df = self.data_reader.get_stock_basic()
            df = df[df["ts_code"].isin(set(ts_codes))]
            return {row["ts_code"]: str(row.get("name") or "") for _, row in df.iterrows()}
        except Exception as e:
            logger.warning(f"获取股票名称失败（ST 判定退化为板块规则）: {e}")
            return {}

    def _limit_pct(self, ts_code: str, stock_names: Dict[str, str]) -> float:
        """返回该股票的涨跌停幅度（小数）。

        北交所 30%，创业板/科创板 20%，ST 5%，主板默认 10%。
        """
        prefix = ts_code.split('.')[0]
        if prefix.startswith(('300', '301', '688', '689')):
            return 0.20
        if prefix.startswith(('8', '4', '92')):
            return 0.30
        name = stock_names.get(ts_code, '')
        if 'ST' in name.upper():
            return 0.05
        return 0.10

    def _get_execution_snapshot(self, exec_date: str,
                                ts_codes: List[str]) -> Tuple[Dict[str, float], Dict[str, Dict[str, bool]]]:
        """获取执行日的价格与可交易性。

        返回:
            prices: {ts_code: close}
            tradability: {ts_code: {'can_buy': bool, 'can_sell': bool}}
                当日无行情 → 停牌，买不了也卖不掉
                涨停 → 不能买入；跌停 → 不能卖出
        """
        prices: Dict[str, float] = {}
        tradability: Dict[str, Dict[str, bool]] = {}
        try:
            if not ts_codes:
                return prices, tradability

            df = self.data_reader.get_daily(
                ts_codes=ts_codes, start_date=exec_date, end_date=exec_date
            )
            if df.empty:
                return prices, tradability

            # 名称信息用于 ST 判定，尽量批量取一次
            names: Dict[str, str] = {}
            try:
                basic = self.data_reader.get_stock_basic()
                basic = basic[basic["ts_code"].isin(set(ts_codes))]
                names = {row["ts_code"]: str(row.get("name") or "") for _, row in basic.iterrows()}
            except Exception as e:
                logger.warning(f"获取股票名称失败（ST 判定退化为板块规则）: {e}")

            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                close = float(row["close"])
                if close <= 0:
                    continue
                prices[ts_code] = close

                pct_chg = row.get("pct_chg")
                pre_close = row.get("pre_close")
                try:
                    if pct_chg is not None and not pd.isna(pct_chg):
                        chg = float(pct_chg) / 100.0
                    elif pre_close is not None and not pd.isna(pre_close) and float(pre_close) > 0:
                        chg = close / float(pre_close) - 1.0
                    else:
                        chg = None
                except (TypeError, ValueError):
                    chg = None

                limit = self._limit_pct(ts_code, names)
                # 留 0.2% 的舍入容差，避免 9.99% 这类未涨停被误判
                limit_up = chg is not None and chg >= limit - 0.002
                limit_down = chg is not None and chg <= -(limit - 0.002)
                tradability[ts_code] = {
                    'can_buy': not limit_up,
                    'can_sell': not limit_down,
                }

            return prices, tradability

        except Exception as e:
            logger.error(f"获取执行日行情失败: {exec_date}, 错误: {e}")
            return prices, tradability
    
    def _calculate_portfolio_value(self, positions: Dict[str, int], 
                                 prices: Dict[str, float], cash: float) -> float:
        """计算组合价值"""
        try:
            positions_value = sum(
                positions.get(ts_code, 0) * prices.get(ts_code, 0)
                for ts_code in positions.keys()
            )
            return positions_value + cash
            
        except Exception as e:
            logger.error(f"计算组合价值失败: {e}")
            return cash
    
    def _apply_trade_costs(self, trade_value: float, commission_rate: float,
                           slippage_rate: float, sell_value: float = 0.0,
                           stamp_duty_rate: float = None) -> Dict[str, float]:
        if stamp_duty_rate is None:
            stamp_duty_rate = Config.DEFAULT_STAMP_DUTY_RATE
        """交易成本：佣金+滑点双边收取，印花税只对卖出方征收。

        A 股印花税为卖方单边强制成本（2023-08-28 起 0.05%），漏掉会系统性
        低估高换手策略的成本，足以改变策略盈亏结论。
        """
        commission = float(trade_value) * float(commission_rate or 0.0)
        slippage = float(trade_value) * float(slippage_rate or 0.0)
        stamp_duty = float(sell_value or 0.0) * float(stamp_duty_rate or 0.0)
        return {
            'commission': commission,
            'slippage': slippage,
            'stamp_duty': stamp_duty,
            'total_cost': commission + slippage + stamp_duty,
        }

    def _rebalance_portfolio(self, current_positions: Dict[str, int],
                           current_cash: float, target_weights: Dict[str, float],
                           prices: Dict[str, float], tradability: Dict[str, Dict[str, bool]],
                           total_value: float,
                           commission_rate: float, slippage_rate: float,
                           stamp_duty_rate: float = None) -> Tuple[Dict[str, int], float, float, Dict[str, float]]:
        if stamp_duty_rate is None:
            stamp_duty_rate = Config.DEFAULT_STAMP_DUTY_RATE
        """执行组合再平衡。

        交易约束:
        - 当日无行情（停牌）或涨停的股票不能买入
        - 当日无行情或跌停的股票不能卖出，原有持仓继续保留在账上
        """
        try:
            new_positions = {}

            # 计算目标持仓
            for ts_code, weight in target_weights.items():
                price = prices.get(ts_code)
                trade_flags = tradability.get(ts_code, {})
                if price is None or price <= 0:
                    continue  # 停牌，无法买入
                if not trade_flags.get('can_buy', True):
                    continue  # 涨停，无法买入
                target_value = total_value * weight
                target_shares = int(target_value / price / 100) * 100  # 按手数调整
                new_positions[ts_code] = target_shares

            # 无法卖出的旧持仓保留（停牌/跌停），不能从账上凭空消失
            for ts_code, shares in current_positions.items():
                if ts_code in new_positions:
                    continue
                price = prices.get(ts_code)
                trade_flags = tradability.get(ts_code, {})
                if price is None or price <= 0 or not trade_flags.get('can_sell', True):
                    if shares > 0:
                        new_positions[ts_code] = shares

            # 计算交易成本和换手率
            total_trade_value = 0.0
            buy_value = 0.0
            sell_value = 0.0
            for ts_code in set(list(current_positions.keys()) + list(new_positions.keys())):
                current_shares = current_positions.get(ts_code, 0)
                new_shares = new_positions.get(ts_code, 0)
                price = prices.get(ts_code)

                if price is not None and price > 0:
                    delta = new_shares - current_shares
                    trade_value = abs(delta) * price
                    total_trade_value += trade_value
                    if delta > 0:
                        buy_value += trade_value
                    elif delta < 0:
                        sell_value += trade_value

            turnover = total_trade_value / total_value if total_value > 0 else 0
            cost_breakdown = self._apply_trade_costs(
                total_trade_value, commission_rate, slippage_rate,
                sell_value=sell_value, stamp_duty_rate=stamp_duty_rate,
            )
            transaction_costs = cost_breakdown['total_cost']

            # 计算新的现金余额
            new_cash = current_cash
            for ts_code in set(list(current_positions.keys()) + list(new_positions.keys())):
                current_shares = current_positions.get(ts_code, 0)
                new_shares = new_positions.get(ts_code, 0)
                price = prices.get(ts_code)

                if price is not None and price > 0:
                    new_cash -= (new_shares - current_shares) * price

            new_cash -= transaction_costs

            return new_positions, new_cash, turnover, cost_breakdown

        except Exception as e:
            logger.error(f"组合再平衡失败: {e}")
            return current_positions, current_cash, 0.0, self._apply_trade_costs(0.0, commission_rate, slippage_rate)
    
    TRADING_DAYS_PER_YEAR = 252

    def _calculate_performance_metrics(self, portfolio_values: List[Dict[str, Any]],
                                     daily_returns: List[float],
                                     start_date: str, end_date: str,
                                     benchmark_returns: List[Dict[str, Any]] = None,
                                     initial_capital: float = None) -> Dict[str, Any]:
        """计算回测指标。

        全部指标基于逐日净值与日频收益，年化统一按 252 个交易日折算，
        与基准年化口径保持一致（此前组合用日历年、基准用交易日，alpha
        的分子两项口径不同会产生系统性偏移）。
        """
        try:
            if not portfolio_values or not daily_returns:
                return {}

            ppy = self.TRADING_DAYS_PER_YEAR
            returns_array = np.array(daily_returns, dtype=float)

            # 基本指标：total_return 统一以初始资金为基准，与响应负载口径一致
            initial_value = initial_capital if initial_capital else portfolio_values[0]['total_value']
            final_value = portfolio_values[-1]['total_value']
            total_return = (final_value - initial_value) / initial_value

            # 年化收益率：按观测到的交易日数折算年限
            n_obs = len(portfolio_values)
            years = n_obs / ppy if n_obs > 0 else 0.0
            annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

            mean_period_return = float(np.mean(returns_array))
            ddof = 1 if len(returns_array) > 1 else 0
            period_volatility = float(np.std(returns_array, ddof=ddof))
            volatility = period_volatility * np.sqrt(ppy)

            # 夏普比率：分子用算术平均超额收益年化。
            # 几何年化收益会随波动率上升而低于算术平均（复利拖累），
            # 用它做分子会让夏普随波动率系统性偏高
            risk_free_rate = 0.03
            rf_period = risk_free_rate / ppy
            sharpe_ratio = (
                (mean_period_return - rf_period) * np.sqrt(ppy) / period_volatility
                if period_volatility > 0 else 0.0
            )

            # 最大回撤（逐日路径）
            values = [pv['total_value'] for pv in portfolio_values]
            peak = values[0]
            max_drawdown = 0
            for value in values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

            # 胜率（日频正收益占比）
            positive_returns = [r for r in daily_returns if r > 0]
            win_rate = len(positive_returns) / len(daily_returns) if daily_returns else 0

            # 卡尔玛比率
            calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0

            # VaR (95%) - 历史模拟法
            var_95 = float(np.percentile(returns_array, 5)) if len(returns_array) > 0 else 0.0

            # CVaR (95%) - 超过 VaR 损失的均值
            cvar_95 = float(np.mean(returns_array[returns_array <= var_95])) if np.any(returns_array <= var_95) else var_95

            # Beta / Alpha / 信息比率：基于同窗口对齐的组合与基准收益
            aligned = self._align_with_benchmark(portfolio_values, daily_returns, benchmark_returns)
            beta = None
            alpha = None
            information_ratio = None
            benchmark_annual = self._calc_benchmark_annual_return(benchmark_returns or [])
            if aligned is not None:
                port_rets, bench_rets = aligned
                bench_var = float(np.var(bench_rets, ddof=1)) if len(bench_rets) > 1 else 0.0
                if bench_var > 0:
                    beta = float(np.cov(port_rets, bench_rets, ddof=1)[0, 1] / bench_var)

                    # 跟踪误差必须是"超额收益序列"的波动率，
                    # 不能拿组合总波动率充数（总波动包含大量基准共同波动）
                    active_returns = port_rets - bench_rets
                    tracking_error = float(np.std(active_returns, ddof=1)) * np.sqrt(ppy)
                    excess_annual = annualized_return - benchmark_annual
                    information_ratio = excess_annual / tracking_error if tracking_error > 0 else None

                    alpha = annualized_return - (risk_free_rate + beta * (benchmark_annual - risk_free_rate))

            return {
                'total_return': total_return,
                'annualized_return': annualized_return,
                'volatility': volatility,
                'sharpe_ratio': float(sharpe_ratio),
                'max_drawdown': max_drawdown,
                'win_rate': win_rate,
                'calmar_ratio': calmar_ratio,
                'total_trades': len(daily_returns),
                'avg_daily_return': mean_period_return,
                'std_daily_return': float(np.std(daily_returns)) if daily_returns else 0,
                'var_95': var_95,
                'cvar_95': cvar_95,
                'beta': beta,
                'alpha': alpha,
                'information_ratio': information_ratio,
                'trading_days': n_obs,
            }

        except Exception as e:
            logger.error(f"计算回测指标失败: {e}")
            return {}

    def _align_with_benchmark(self, portfolio_values: List[Dict[str, Any]],
                              daily_returns: List[float],
                              benchmark_returns: List[Dict[str, Any]]):
        """把组合区间收益与基准在同区间内的复合收益对齐。

        组合每一期是 [date_{i-1}, date_i] 的区间收益，因此基准日收益
        必须按同样的窗口复合，直接按位置截断对齐会把不相关日期的收益
        混在一起。返回 (port_rets, bench_rets) 或 None。
        """
        try:
            if len(portfolio_values) < 2 or not daily_returns or not benchmark_returns:
                return None

            bench_records = []
            for row in benchmark_returns:
                ret = row.get('daily_return')
                if ret is None:
                    continue
                bench_records.append((pd.to_datetime(row['date']).normalize(), float(ret)))
            bench_records.sort(key=lambda item: item[0])
            if not bench_records:
                return None

            bench_dates = np.array([r[0] for r in bench_records])
            bench_rets_all = np.array([r[1] for r in bench_records])

            port_dates = [pd.to_datetime(pv['date']).normalize() for pv in portfolio_values]
            window_bench_returns = []
            aligned_port_returns = []
            for prev_date, cur_date, port_ret in zip(port_dates[:-1], port_dates[1:], daily_returns):
                mask = (bench_dates > prev_date) & (bench_dates <= cur_date)
                segment = bench_rets_all[mask]
                if len(segment) == 0:
                    continue
                window_bench_returns.append(float(np.prod(1.0 + segment) - 1.0))
                aligned_port_returns.append(float(port_ret))

            if len(window_bench_returns) < 2:
                return None
            return np.array(aligned_port_returns), np.array(window_bench_returns)
        except Exception:
            return None

    def _calc_benchmark_annual_return(self, benchmark_returns: List[Dict[str, Any]]) -> float:
        """从基准累计收益计算年化收益。"""
        try:
            if not benchmark_returns:
                return 0.0
            first = benchmark_returns[0].get('close', 0)
            last = benchmark_returns[-1].get('close', 0)
            if not first or not last:
                return 0.0
            total = (last - first) / first
            days = len(benchmark_returns)
            years = days / 252
            if years <= 0:
                return 0.0
            return (1 + total) ** (1 / years) - 1
        except Exception:
            return 0.0

    def _get_benchmark_returns(self, start_date: str, end_date: str, benchmark_code: str = "000300.SH") -> List[Dict[str, Any]]:
        """获取基准收益率"""
        try:
            benchmark_codes = [benchmark_code, "000300.SH", "399300.SZ"]

            for code in benchmark_codes:
                df = self.data_reader.get_daily(
                    ts_codes=[code], start_date=start_date, end_date=end_date
                )
                if not df.empty:
                    break
            else:
                return []

            if df.empty:
                return []

            df = df.sort_values("trade_date")
            returns = []
            prev_close = None
            base_close = None

            for _, row in df.iterrows():
                close = row.get("close")
                if close is None or pd.isna(close):
                    continue

                close_price = float(close)
                if close_price <= 0:
                    continue

                if base_close is None:
                    base_close = close_price

                if prev_close is None or prev_close <= 0:
                    daily_return = 0.0
                else:
                    daily_return = (close_price - prev_close) / prev_close

                cumulative_return = (close_price / base_close - 1.0) if base_close else 0.0
                trade_date_val = row["trade_date"]
                date_text = trade_date_val.isoformat() if hasattr(trade_date_val, "isoformat") else str(trade_date_val)

                returns.append({
                    "date": date_text,
                    "close": close_price,
                    "daily_return": daily_return,
                    "cumulative_return": cumulative_return,
                    "value": 1.0 + cumulative_return,
                })

                prev_close = close_price

            return returns
            
        except Exception as e:
            logger.error(f"获取基准收益率失败: {e}")
            return []

    def _get_stock_metadata(self, ts_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取股票名称和行业信息"""
        try:
            if not ts_codes:
                return {}
            df = self.data_reader.get_stock_basic()
            df = df[df["ts_code"].isin(set(ts_codes))]
            return {
                row["ts_code"]: {
                    'name': row.get("name") or row["ts_code"],
                    'industry': row.get("industry") or '未知'
                }
                for _, row in df.iterrows()
            }
        except Exception as e:
            logger.error(f"获取股票元数据失败: {e}")
            return {}

    def _build_equity_curve(
        self,
        portfolio_values: List[Dict[str, Any]],
        benchmark_returns: List[Dict[str, Any]],
        initial_capital: float,
    ) -> List[Dict[str, Any]]:
        benchmark_map = {row['date']: row.get('value') for row in benchmark_returns}
        return [
            {
                'date': item['date'],
                'portfolio': item['total_value'] / initial_capital if initial_capital else None,
                'benchmark': benchmark_map.get(item['date']),
            }
            for item in portfolio_values
        ]

    def _build_drawdown_series(self, portfolio_values: List[Dict[str, Any]], initial_capital: float) -> List[Dict[str, Any]]:
        data = []
        max_value = initial_capital
        for item in portfolio_values:
            current_value = item['total_value']
            max_value = max(max_value, current_value)
            drawdown = (current_value - max_value) / max_value if max_value else 0
            data.append({'date': item['date'], 'drawdown': drawdown})
        return data

    def _build_monthly_returns(
        self,
        portfolio_values: List[Dict[str, Any]],
        benchmark_returns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if len(portfolio_values) < 2:
            return []

        benchmark_map = {row['date']: row.get('value') for row in benchmark_returns}
        monthly_groups: Dict[str, Dict[str, Any]] = {}
        for index in range(1, len(portfolio_values)):
            current_item = portfolio_values[index]
            previous_item = portfolio_values[index - 1]
            date_text = current_item['date']
            month_key = str(date_text)[:7]
            portfolio_return = (
                current_item['total_value'] / previous_item['total_value'] - 1
                if previous_item['total_value'] else 0
            )
            benchmark_value = benchmark_map.get(date_text)
            previous_benchmark_value = benchmark_map.get(previous_item['date'])
            benchmark_return = None
            if benchmark_value is not None and previous_benchmark_value not in (None, 0):
                benchmark_return = benchmark_value / previous_benchmark_value - 1

            group = monthly_groups.setdefault(month_key, {'date': month_key, 'portfolio': 1.0, 'benchmark': 1.0})
            group['portfolio'] *= (1 + portfolio_return)
            if benchmark_return is not None:
                group['benchmark'] *= (1 + benchmark_return)

        results = []
        for group in monthly_groups.values():
            benchmark_value = group['benchmark'] - 1 if group['benchmark'] != 1.0 else None
            results.append({
                'date': group['date'],
                'portfolio': group['portfolio'] - 1,
                'benchmark': benchmark_value,
            })
        return results

    def _build_returns_distribution(self, daily_returns: List[float]) -> List[Dict[str, Any]]:
        if not daily_returns:
            return []
        bins = [i / 100 for i in range(-10, 11)]
        distribution = []
        for bin_value in bins:
            count = len([ret for ret in daily_returns if ret >= bin_value - 0.005 and ret < bin_value + 0.005])
            distribution.append({'returns': bin_value, 'frequency': count})
        return distribution

    def _build_position_summary(
        self,
        daily_positions: List[Dict[str, int]],
        final_prices: Dict[str, float],
        final_value: float,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        if not daily_positions:
            return []
        last_positions = daily_positions[-1] or {}
        metadata = self._get_stock_metadata(list(last_positions.keys()))
        positions = []
        for ts_code, shares in last_positions.items():
            price = final_prices.get(ts_code, 0.0)
            weight = (shares * price / final_value) if final_value and price else 0.0
            info = metadata.get(ts_code, {'name': ts_code, 'industry': '未知'})
            positions.append({
                'code': ts_code,
                'name': info.get('name', ts_code),
                'industry': info.get('industry', '未知'),
                'weight': weight,
                'period': f'{start_date} ~ {end_date}',
                'return': None,
                'contribution': None,
            })
        return positions

    def _build_industry_distribution(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        industry_weights: Dict[str, float] = {}
        for position in positions:
            industry = position.get('industry') or '未知'
            industry_weights[industry] = industry_weights.get(industry, 0.0) + float(position.get('weight') or 0.0)
        return [
            {'name': name, 'value': value}
            for name, value in sorted(industry_weights.items(), key=lambda item: item[1], reverse=True)
        ]

    def _build_risk_metrics(self, performance_metrics: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'var_95': performance_metrics.get('var_95'),
            'cvar_95': performance_metrics.get('cvar_95'),
            'beta': performance_metrics.get('beta'),
            'alpha': performance_metrics.get('alpha'),
            'information_ratio': performance_metrics.get('information_ratio'),
            'calmar_ratio': performance_metrics.get('calmar_ratio'),
        }

    def _build_execution_assumptions(self, strategy_config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'commission_rate': float(strategy_config.get('commission_rate', 0.001)),
            'slippage_rate': float(strategy_config.get('slippage_rate', 0.0)),
            'stamp_duty_rate': float(strategy_config.get('stamp_duty_rate', Config.DEFAULT_STAMP_DUTY_RATE)),
            'benchmark_index': strategy_config.get('benchmark_index', '000300.SH'),
            'execution_price': 'next_trade_day_close',
        }

    def _build_trade_constraints(self, strategy_config: Dict[str, Any]) -> Dict[str, Any]:
        """回测实际执行的交易约束（供前端展示，与引擎行为一致）。

        - 停牌（当日无行情）：不买入，持仓保留
        - 涨停不买入、跌停不卖出（ST 5%，创业板/科创板 20%，北交所 30%，主板 10%）
        - 信号 t 日产生，t+1 收盘成交
        """
        return {
            'max_position_count': int(strategy_config.get('top_n', 50)),
            'min_trade_weight': float(strategy_config.get('min_trade_weight', 0.0)),
            'suspend_policy': 'no_buy_keep_position',
            'limit_up_down_policy': 'enforced_at_execution',
            'execution_timing': 't_plus_1_close',
        }

    def _normalize_benchmark_returns(self, benchmark_returns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in benchmark_returns or []:
            item = dict(row)
            if item.get('value') is None:
                cumulative_return = item.get('cumulative_return')
                item['value'] = 1.0 + cumulative_return if cumulative_return is not None else None
            normalized.append(item)
        return normalized

    def _build_response_payload(
        self,
        strategy_config: Dict[str, Any],
        start_date: str,
        end_date: str,
        initial_capital: float,
        final_value: float,
        portfolio_values: List[Dict[str, Any]],
        daily_returns: List[float],
        daily_positions: List[Dict[str, int]],
        daily_turnover: List[float],
        performance_metrics: Dict[str, Any],
        benchmark_returns: List[Dict[str, Any]],
        final_prices: Dict[str, float],
        run_id: Optional[int] = None,
        execution_assumptions: Optional[Dict[str, Any]] = None,
        trade_constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        performance_metrics = dict(performance_metrics or {})
        benchmark_returns = self._normalize_benchmark_returns(benchmark_returns)
        if 'annualized_return' in performance_metrics and 'annual_return' not in performance_metrics:
            performance_metrics['annual_return'] = performance_metrics['annualized_return']
        positions = self._build_position_summary(daily_positions, final_prices, final_value, start_date, end_date)
        industry_distribution = self._build_industry_distribution(positions)
        return {
            'success': True,
            'run_id': run_id,
            'strategy_config': strategy_config,
            'backtest_period': f"{start_date} to {end_date}",
            'initial_capital': initial_capital,
            'final_value': final_value,
            'total_return': (final_value - initial_capital) / initial_capital if initial_capital else None,
            'portfolio_values': portfolio_values,
            'daily_returns': daily_returns,
            'daily_positions': daily_positions,
            'daily_turnover': daily_turnover,
            'performance_metrics': performance_metrics,
            'benchmark_returns': benchmark_returns,
            'equity_curve': self._build_equity_curve(portfolio_values, benchmark_returns, initial_capital),
            'drawdown_series': self._build_drawdown_series(portfolio_values, initial_capital),
            'monthly_returns': self._build_monthly_returns(portfolio_values, benchmark_returns),
            'returns_distribution': self._build_returns_distribution(daily_returns),
            'positions': positions,
            'industry_distribution': industry_distribution,
            'risk_metrics': self._build_risk_metrics(performance_metrics),
            'execution_assumptions': execution_assumptions or {},
            'trade_constraints': trade_constraints or {},
        }
    
    def compare_strategies(self, strategies: List[Dict[str, Any]], 
                         start_date: str, end_date: str) -> Dict[str, Any]:
        """比较多个策略"""
        try:
            results = []
            
            for i, strategy in enumerate(strategies):
                logger.info(f"回测策略 {i+1}: {strategy.get('name', f'Strategy_{i+1}')}")
                
                result = self.run_backtest(
                    strategy['config'], start_date, end_date,
                    strategy.get('initial_capital', 1000000.0),
                    strategy.get('rebalance_frequency', 'monthly')
                )
                
                if result.get('success'):
                    results.append({
                        'strategy_name': strategy.get('name', f'Strategy_{i+1}'),
                        'result': result
                    })
            
            # 生成比较报告
            comparison = self._generate_comparison_report(results)
            
            return {
                'success': True,
                'strategies': results,
                'comparison': comparison
            }
            
        except Exception as e:
            logger.error(f"策略比较失败: {e}")
            return {'error': str(e)}
    
    def _generate_comparison_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成策略比较报告"""
        try:
            if not results:
                return {}
            
            comparison_metrics = {}
            
            for result in results:
                strategy_name = result['strategy_name']
                metrics = result['result']['performance_metrics']
                
                comparison_metrics[strategy_name] = {
                    'total_return': metrics.get('total_return', 0),
                    'annualized_return': metrics.get('annualized_return', 0),
                    'volatility': metrics.get('volatility', 0),
                    'sharpe_ratio': metrics.get('sharpe_ratio', 0),
                    'max_drawdown': metrics.get('max_drawdown', 0),
                    'win_rate': metrics.get('win_rate', 0),
                    'calmar_ratio': metrics.get('calmar_ratio', 0)
                }
            
            # 找出最佳策略
            best_strategy = {
                'highest_return': max(comparison_metrics.items(), 
                                    key=lambda x: x[1]['total_return'])[0],
                'highest_sharpe': max(comparison_metrics.items(), 
                                    key=lambda x: x[1]['sharpe_ratio'])[0],
                'lowest_drawdown': min(comparison_metrics.items(), 
                                     key=lambda x: x[1]['max_drawdown'])[0],
                'highest_win_rate': max(comparison_metrics.items(), 
                                      key=lambda x: x[1]['win_rate'])[0]
            }
            
            return {
                'metrics_comparison': comparison_metrics,
                'best_strategy': best_strategy,
                'summary': {
                    'total_strategies': len(results),
                    'avg_return': np.mean([m['total_return'] for m in comparison_metrics.values()]),
                    'avg_sharpe': np.mean([m['sharpe_ratio'] for m in comparison_metrics.values()]),
                    'avg_drawdown': np.mean([m['max_drawdown'] for m in comparison_metrics.values()])
                }
            }
            
        except Exception as e:
            logger.error(f"生成比较报告失败: {e}")
            return {} 
