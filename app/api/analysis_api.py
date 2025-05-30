from flask import request, jsonify
from app.api import api_bp
from app.services.stock_service import StockService
from loguru import logger
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

@api_bp.route('/analysis/screen', methods=['POST'])
def screen_stocks():
    """股票筛选"""
    try:
        data = request.get_json()
        logger.info(f"收到筛选请求: {data}")
        
        # 使用StockService进行筛选
        result = StockService.screen_stocks(data)
        
        return jsonify({
            'code': 200,
            'message': '筛选完成',
            'data': result
        })
    except Exception as e:
        logger.error(f"股票筛选API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

@api_bp.route('/analysis/backtest', methods=['POST'])
def backtest_strategy():
    """策略回测"""
    try:
        data = request.get_json()
        logger.info(f"收到回测请求: {data}")
        
        # 验证必要参数
        required_fields = ['ts_code', 'strategy_type', 'start_date', 'end_date', 'initial_capital']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'code': 400,
                    'message': f'缺少必要参数: {field}',
                    'data': None
                }), 400
        
        # 获取历史数据
        ts_code = data['ts_code']
        start_date = data['start_date']
        end_date = data['end_date']
        
        # 获取更多历史数据用于计算技术指标
        extended_start = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=100)
        extended_start_str = extended_start.strftime('%Y-%m-%d')
        
        history_data = StockService.get_daily_history(
            ts_code, 
            start_date=extended_start_str, 
            end_date=end_date, 
            limit=500
        )
        
        if not history_data or len(history_data) < 30:
            return jsonify({
                'code': 400,
                'message': '历史数据不足，无法进行回测',
                'data': None
            }), 400
        
        # 获取技术因子数据
        factors_data = StockService.get_stock_factors(
            ts_code,
            start_date=extended_start_str,
            end_date=end_date,
            limit=500
        )
        
        # 执行回测
        backtest_engine = BacktestEngine(data)
        result = backtest_engine.run_backtest(history_data, factors_data)
        
        return jsonify({
            'code': 200,
            'message': '回测完成',
            'data': result
        })
        
    except Exception as e:
        logger.error(f"策略回测API错误: {e}")
        return jsonify({
            'code': 500,
            'message': f'回测失败: {str(e)}',
            'data': None
        }), 500


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, config):
        self.config = config
        self.ts_code = config['ts_code']
        self.strategy_type = config['strategy_type']
        self.start_date = config['start_date']
        self.end_date = config['end_date']
        self.initial_capital = config['initial_capital']
        self.commission_rate = config.get('commission_rate', 0.001)
        self.params = config.get('params', {})
        
        # 回测状态
        self.cash = self.initial_capital
        self.position = 0  # 持仓数量
        self.trades = []
        self.daily_values = []
        
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
            # 从超买区域向下突破卖出
            elif current_rsi < overbought and prev_rsi >= overbought:
                df.iloc[i, df.columns.get_loc('signal')] = -1
        
        return df
    
    def _bollinger_strategy(self, df):
        """布林带策略"""
        for i in range(len(df)):
            close = df.iloc[i]['close']
            boll_upper = df.iloc[i]['boll_upper'] if pd.notna(df.iloc[i]['boll_upper']) else close
            boll_lower = df.iloc[i]['boll_lower'] if pd.notna(df.iloc[i]['boll_lower']) else close
            
            # 价格触及下轨买入
            if close <= boll_lower and boll_lower > 0:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            # 价格触及上轨卖出
            elif close >= boll_upper and boll_upper > 0:
                df.iloc[i, df.columns.get_loc('signal')] = -1
        
        return df
    
    def _execute_trades(self, df):
        """执行交易"""
        for i, row in df.iterrows():
            signal = row['signal']
            price = row['close']
            date = row['trade_date'].strftime('%Y-%m-%d')
            
            if signal == 1 and self.position == 0:  # 买入
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
            
            elif signal == -1 and self.position > 0:  # 卖出
                commission = self.position * price * self.commission_rate
                total_income = self.position * price - commission
                
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
        
        # 最终清仓
        final_price = df.iloc[-1]['close']
        if self.position > 0:
            commission = self.position * final_price * self.commission_rate
            self.cash += self.position * final_price - commission
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
        
        # 计算夏普比率
        risk_free_rate = 0.03  # 假设无风险利率3%
        sharpe_ratio = (annual_return - risk_free_rate) / volatility if volatility > 0 else 0
        
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
        
        # 计算总手续费
        total_commission = sum(t['commission'] for t in self.trades if 'commission' in t)
        
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