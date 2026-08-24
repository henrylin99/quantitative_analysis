"""单股票技术策略回测引擎。

从 app/api/analysis_api.py 抽取（原为 API 文件内定义的 335 行引擎，
与服务层 app/services/backtest_engine.py 的多因子组合回测是两套不同语义）。

交易规则: 信号在 t 日收盘后产生，t+1 收盘成交（防未来函数）。
"""

import pandas as pd
import numpy as np
from config import Config
from datetime import datetime
from loguru import logger


class SingleStockBacktestEngine:
    """单股票技术指标策略回测引擎"""

    def __init__(self, config):
        self.config = config
        self.ts_code = config['ts_code']
        self.strategy_type = config['strategy_type']
        self.start_date = config['start_date']
        self.end_date = config['end_date']
        self.initial_capital = config['initial_capital']
        self.commission_rate = config.get('commission_rate', 0.001)
        # A 股印花税：卖方单边强制成本（2023-08-28 起 0.05%）
        self.stamp_duty_rate = config.get('stamp_duty_rate', Config.DEFAULT_STAMP_DUTY_RATE)
        self.params = config.get('params', {})

        # 回测状态
        self.cash = self.initial_capital
        self.position = 0  # 持仓数量
        self.trades = []
        self.daily_values = []
        self.liquidation_cost = 0.0  # 期末强平成本，_calculate_performance 中更新

    def run_backtest(self, history_data, factors_data):
        """运行回测"""
        try:
            # 转换为DataFrame
            df_history = pd.DataFrame(history_data)
            df_factors = pd.DataFrame(factors_data)

            # 合并数据
            df = self._merge_data(df_history, df_factors)

            # 筛选回测期间的数据
            df = df[(df['trade_date'] >= self.start_date) & (df['trade_date'] <= self.end_date)]

            if len(df) < 10:
                raise ValueError("回测期间数据不足")

            df = df.reset_index(drop=True)

            # 计算策略信号
            df = self._calculate_signals(df)

            # 执行交易
            self._execute_trades(df)

            # 计算绩效指标
            performance = self._calculate_performance(df)

            return {
                'performance': performance,
                'trades': self.trades[-20:],  # 返回最近20笔交易
                'config': self.config
            }

        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            raise

    def _merge_data(self, df_history, df_factors):
        """合并历史数据和技术因子数据"""
        df_history['trade_date'] = pd.to_datetime(df_history['trade_date'])
        df_factors['trade_date'] = pd.to_datetime(df_factors['trade_date'])

        # 合并数据
        df = pd.merge(df_history, df_factors, on='trade_date', how='left', suffixes=('', '_factor'))
        df = df.sort_values('trade_date').reset_index(drop=True)

        return df

    def _calculate_signals(self, df):
        """计算策略信号"""
        df['signal'] = 0  # 0: 无操作, 1: 买入, -1: 卖出

        if self.strategy_type == 'ma_cross':
            df = self._ma_cross_strategy(df)
        elif self.strategy_type == 'macd':
            df = self._macd_strategy(df)
        elif self.strategy_type == 'kdj':
            df = self._kdj_strategy(df)
        elif self.strategy_type == 'rsi':
            df = self._rsi_strategy(df)
        elif self.strategy_type == 'bollinger':
            df = self._bollinger_strategy(df)

        return df

    def _ma_cross_strategy(self, df):
        """均线交叉策略"""
        ma_short = self.params.get('ma_short', 5)
        ma_long = self.params.get('ma_long', 20)

        # 计算均线
        df['ma_short'] = df['close'].rolling(window=ma_short).mean()
        df['ma_long'] = df['close'].rolling(window=ma_long).mean()

        # 生成信号
        for i in range(1, len(df)):
            if (df.iloc[i]['ma_short'] > df.iloc[i]['ma_long'] and
                df.iloc[i-1]['ma_short'] <= df.iloc[i-1]['ma_long']):
                df.iloc[i, df.columns.get_loc('signal')] = 1  # 买入信号
            elif (df.iloc[i]['ma_short'] < df.iloc[i]['ma_long'] and
                  df.iloc[i-1]['ma_short'] >= df.iloc[i-1]['ma_long']):
                df.iloc[i, df.columns.get_loc('signal')] = -1  # 卖出信号

        return df

    def _macd_strategy(self, df):
        """MACD策略"""
        # 使用已计算的MACD数据
        for i in range(1, len(df)):
            current_macd = df.iloc[i]['macd'] if pd.notna(df.iloc[i]['macd']) else 0
            current_dea = df.iloc[i]['macd_dea'] if pd.notna(df.iloc[i]['macd_dea']) else 0
            prev_macd = df.iloc[i-1]['macd'] if pd.notna(df.iloc[i-1]['macd']) else 0
            prev_dea = df.iloc[i-1]['macd_dea'] if pd.notna(df.iloc[i-1]['macd_dea']) else 0

            # MACD上穿DEA买入，下穿卖出
            if current_macd > current_dea and prev_macd <= prev_dea:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            elif current_macd < current_dea and prev_macd >= prev_dea:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        return df

    def _kdj_strategy(self, df):
        """KDJ策略"""
        oversold = self.params.get('oversold', 20)
        overbought = self.params.get('overbought', 80)

        for i in range(1, len(df)):
            current_k = df.iloc[i]['kdj_k'] if pd.notna(df.iloc[i]['kdj_k']) else 50
            prev_k = df.iloc[i-1]['kdj_k'] if pd.notna(df.iloc[i-1]['kdj_k']) else 50

            # 从超卖区域向上突破买入
            if current_k > oversold and prev_k <= oversold:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            # 从超买区域向下突破卖出
            elif current_k < overbought and prev_k >= overbought:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        return df

    def _rsi_strategy(self, df):
        """RSI策略"""
        oversold = self.params.get('oversold', 30)
        overbought = self.params.get('overbought', 70)

        for i in range(1, len(df)):
            current_rsi = df.iloc[i]['rsi_6'] if pd.notna(df.iloc[i]['rsi_6']) else 50
            prev_rsi = df.iloc[i-1]['rsi_6'] if pd.notna(df.iloc[i-1]['rsi_6']) else 50

            # 从超卖区域向上突破买入
            if current_rsi > oversold and prev_rsi <= oversold:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            elif current_rsi < overbought and prev_rsi >= overbought:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        return df

    def _bollinger_strategy(self, df):
        """布林带策略"""
        for i in range(len(df)):
            close = df.iloc[i]['close']
            boll_upper = df.iloc[i]['boll_upper']
            boll_lower = df.iloc[i]['boll_lower']

            # 轨道尚未成形（滚动窗口不足，NaN）时跳过。
            # 旧实现用 close 兜底 NaN 轨道，首根 bar 就会触发"触及下轨"买入
            if pd.isna(boll_upper) or pd.isna(boll_lower):
                continue

            # 价格触及下轨买入
            if close <= boll_lower and boll_lower > 0:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            # 价格触及上轨卖出
            elif close >= boll_upper and boll_upper > 0:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        return df

    def _limit_threshold(self) -> float:
        """涨跌停判定阈值。

        这里拿不到股票名称/板块信息，无法区分 ST(5%) 与创业板/科创板(20%)，
        统一用主板 10% 减去容差。对主板股票是精确的；对 20% 涨跌幅品种
        只会漏判极端一字板，属于可接受的保守近似。
        """
        return 0.098

    def _is_suspended(self, row: pd.Series) -> bool:
        """当日无成交（停牌）：按量价为 0 或缺失判定。"""
        vol = row.get('vol')
        close = row.get('close')
        if close is None or pd.isna(close) or float(close) <= 0:
            return True
        if vol is not None and not pd.isna(vol) and float(vol) <= 0:
            return True
        return False

    def _limit_flags(self, row: pd.Series) -> tuple:
        """返回 (涨停不可买, 跌停不可卖)。"""
        close = float(row['close'])
        pct_chg = row.get('pct_chg')
        pre_close = row.get('pre_close')
        try:
            if pct_chg is not None and not pd.isna(pct_chg):
                chg = float(pct_chg) / 100.0
            elif pre_close is not None and not pd.isna(pre_close) and float(pre_close) > 0:
                chg = close / float(pre_close) - 1.0
            else:
                return False, False
        except (TypeError, ValueError):
            return False, False

        threshold = self._limit_threshold()
        return chg >= threshold, chg <= -threshold

    def _execute_trades(self, df):
        """执行交易：信号在 t 日收盘后产生，t+1 收盘成交。

        当日收盘才能确认的信号按当日收盘价成交是未来函数，
        因此这里用 pending_signal 把执行推迟到下一根 bar。

        可成交性约束（与多因子回测引擎口径一致）：
        - 停牌（无成交）不交易
        - 涨停不买入、跌停不卖出——反转类策略的超卖反弹日常见一字涨停，
          无条件成交会系统性高估此类策略收益
        - 卖出加收印花税（卖方单边）
        """
        pending_signal = 0
        limit_threshold = self._limit_threshold()
        for i in range(len(df)):
            row = df.iloc[i]
            price = row['close']
            date = row['trade_date'].strftime('%Y-%m-%d')

            # 执行上一根 bar 产生的信号（今日收盘价成交）
            signal = pending_signal
            pending_signal = int(row['signal']) if not pd.isna(row['signal']) else 0

            suspended = self._is_suspended(row)
            limit_up, limit_down = (False, False) if suspended else self._limit_flags(row)

            if signal == 1 and self.position == 0 and not suspended and not limit_up:  # 买入
                # 计算可买入数量（按手，1手=100股）
                max_shares = int(self.cash / price / 100) * 100
                if max_shares >= 100:  # 至少买入1手
                    commission = max_shares * price * self.commission_rate
                    total_cost = max_shares * price + commission

                    if total_cost <= self.cash:
                        self.cash -= total_cost
                        self.position = max_shares

                        self.trades.append({
                            'date': date,
                            'action': 'buy',
                            'price': price,
                            'quantity': max_shares,
                            'amount': total_cost,
                            'commission': commission,
                            'return_rate': None
                        })

            elif signal == -1 and self.position > 0 and not suspended and not limit_down:  # 卖出
                commission = self.position * price * self.commission_rate
                stamp_duty = self.position * price * self.stamp_duty_rate
                total_income = self.position * price - commission - stamp_duty

                # 计算收益率
                buy_trade = None
                for trade in reversed(self.trades):
                    if trade['action'] == 'buy':
                        buy_trade = trade
                        break

                return_rate = 0
                if buy_trade:
                    return_rate = (total_income - buy_trade['amount']) / buy_trade['amount']

                sell_quantity = self.position

                self.cash += total_income
                self.position = 0

                self.trades.append({
                    'date': date,
                    'action': 'sell',
                    'price': price,
                    'quantity': sell_quantity,
                    'amount': total_income,
                    'commission': commission,
                    'stamp_duty': stamp_duty,
                    'return_rate': return_rate
                })

            # 记录每日资产价值
            portfolio_value = self.cash + self.position * price
            self.daily_values.append({
                'date': date,
                'cash': self.cash,
                'position_value': self.position * price,
                'total_value': portfolio_value
            })

    def _calculate_performance(self, df):
        """计算绩效指标"""
        if not self.daily_values:
            return self._get_default_performance()

        # 最终清仓（期末强平的手续费同样要计入总成本统计）
        final_price = df.iloc[-1]['close']
        if self.position > 0:
            commission = self.position * final_price * self.commission_rate
            stamp_duty = self.position * final_price * self.stamp_duty_rate
            self.cash += self.position * final_price - commission - stamp_duty
            self.liquidation_cost = commission + stamp_duty
            self.position = 0

        final_capital = self.cash
        total_return = (final_capital - self.initial_capital) / self.initial_capital

        # 计算年化收益率
        days = len(df)
        annual_return = (final_capital / self.initial_capital) ** (252 / days) - 1 if days > 0 else 0

        # 计算最大回撤
        values = [dv['total_value'] for dv in self.daily_values]
        peak = values[0]
        max_drawdown = 0
        for value in values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)

        # 计算波动率
        returns = []
        for i in range(1, len(values)):
            daily_return = (values[i] - values[i-1]) / values[i-1]
            returns.append(daily_return)

        volatility = np.std(returns) * np.sqrt(252) if returns else 0

        # 计算夏普比率：分子用算术平均超额收益年化，
        # 几何年化做分子会随波动率上升系统性偏高
        risk_free_rate = 0.03  # 假设无风险利率3%
        rf_daily = risk_free_rate / 252
        mean_daily = float(np.mean(returns)) if returns else 0.0
        sharpe_ratio = (
            (mean_daily - rf_daily) * np.sqrt(252) / np.std(returns)
            if returns and np.std(returns) > 0 else 0
        )

        # 交易统计
        buy_trades = [t for t in self.trades if t['action'] == 'buy']
        sell_trades = [t for t in self.trades if t['action'] == 'sell' and t['return_rate'] is not None]
        winning_trades = len([t for t in sell_trades if t['return_rate'] > 0])
        win_rate = winning_trades / len(sell_trades) if sell_trades else 0

        # 计算平均持仓天数
        avg_holding_days = 0
        if len(buy_trades) > 0 and len(sell_trades) > 0:
            holding_periods = []
            for i, sell_trade in enumerate(sell_trades):
                if i < len(buy_trades):
                    buy_date = datetime.strptime(buy_trades[i]['date'], '%Y-%m-%d')
                    sell_date = datetime.strptime(sell_trade['date'], '%Y-%m-%d')
                    holding_periods.append((sell_date - buy_date).days)
            avg_holding_days = np.mean(holding_periods) if holding_periods else 0

        # 计算基准收益率（买入持有策略）
        start_price = df.iloc[0]['close']
        end_price = df.iloc[-1]['close']
        benchmark_return = (end_price - start_price) / start_price

        # 计算总手续费：佣金 + 印花税 + 期末强平成本
        total_commission = sum(t['commission'] for t in self.trades if 'commission' in t)
        total_commission += sum(t['stamp_duty'] for t in self.trades if 'stamp_duty' in t)
        total_commission += self.liquidation_cost

        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'volatility': volatility,
            'win_rate': win_rate,
            'total_trades': len(self.trades),
            'winning_trades': winning_trades,
            'avg_holding_days': round(avg_holding_days, 1),
            'final_capital': final_capital,
            'total_commission': total_commission,
            'benchmark_return': benchmark_return
        }

    def _get_default_performance(self):
        """获取默认绩效指标（无交易情况）"""
        return {
            'total_return': 0.0,
            'annual_return': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'volatility': 0.0,
            'win_rate': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'avg_holding_days': 0,
            'final_capital': self.initial_capital,
            'total_commission': 0.0,
            'benchmark_return': 0.0
        }
