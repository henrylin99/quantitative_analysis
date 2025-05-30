#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级自定义因子库
包含各种复杂的量化因子计算，基于数据库中的多表数据
"""

import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class AdvancedFactorLibrary:
    """高级因子库"""
    
    def __init__(self, host='localhost', user='root', password='root', 
                 database='stock_cursor', charset='utf8mb4'):
        """初始化数据库连接"""
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.connection = None
        self.connect()
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor
            )
            print(f"✅ 成功连接到数据库: {self.database}")
            return True
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            print("🔒 数据库连接已关闭")
    
    def calculate_alpha_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算Alpha因子 - 基于WorldQuant Alpha101"""
        print("\n🎯 计算Alpha因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"h.ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"h.trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"h.trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            h.ts_code,
            h.trade_date,
            h.open,
            h.high,
            h.low,
            h.close,
            h.vol,
            h.amount,
            h.pct_chg,
            
            d.turnover_rate,
            d.pe,
            d.pb,
            d.total_mv,
            d.circ_mv,
            
            -- 获取前一日数据用于计算
            LAG(h.close, 1) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as prev_close,
            LAG(h.vol, 1) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as prev_vol,
            LAG(h.amount, 1) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as prev_amount,
            
            -- 获取多日前数据
            LAG(h.close, 5) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as close_5d,
            LAG(h.close, 10) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as close_10d,
            LAG(h.close, 20) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as close_20d,
            
            -- 移动平均
            AVG(h.close) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma5,
            AVG(h.close) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma10,
            AVG(h.close) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma20,
            
            -- 成交量移动平均
            AVG(h.vol) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as vol_ma5,
            AVG(h.vol) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20,
            
            -- 标准差
            STDDEV(h.close) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as std_20d,
            STDDEV(h.pct_chg) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ret_std_20d
            
        FROM stock_daily_history h
        LEFT JOIN stock_daily_basic d ON h.ts_code = d.ts_code AND h.trade_date = d.trade_date
        WHERE {where_clause}
        ORDER BY h.ts_code, h.trade_date
        """
        
        try:
            df = pd.read_sql(query, self.connection)
            
            # Alpha001: (rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)
            df['returns'] = df['pct_chg'] / 100
            df['signed_power'] = np.where(df['returns'] < 0, df['ret_std_20d'], df['close']) ** 2
            df['alpha001'] = df.groupby('ts_code')['signed_power'].rolling(5).apply(lambda x: np.argmax(x)).reset_index(0, drop=True) - 0.5
            
            # Alpha002: (-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))
            df['log_vol'] = np.log(df['vol'] + 1)
            df['delta_log_vol'] = df.groupby('ts_code')['log_vol'].diff(2)
            df['price_change_ratio'] = (df['close'] - df['open']) / df['open']
            
            def calc_rolling_corr(group):
                return group['delta_log_vol'].rolling(6).corr(group['price_change_ratio'])
            
            df['alpha002'] = -1 * df.groupby('ts_code').apply(calc_rolling_corr).reset_index(0, drop=True)
            
            # Alpha003: (-1 * correlation(rank(open), rank(volume), 10))
            def calc_open_vol_corr(group):
                return group['open'].rolling(10).corr(group['vol'])
            
            df['alpha003'] = -1 * df.groupby('ts_code').apply(calc_open_vol_corr).reset_index(0, drop=True)
            
            # Alpha004: (-1 * Ts_Rank(rank(low), 9))
            df['rank_low'] = df.groupby('trade_date')['low'].rank()
            df['alpha004'] = -1 * df.groupby('ts_code')['rank_low'].rolling(9).rank().reset_index(0, drop=True)
            
            # Alpha005: (rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))
            df['vwap'] = df['amount'] / df['vol']  # 成交额/成交量 = VWAP
            df['vwap_ma10'] = df.groupby('ts_code')['vwap'].rolling(10).mean().reset_index(0, drop=True)
            df['rank_open_vwap'] = df.groupby('trade_date')['open'].rank() - df.groupby('trade_date')['vwap_ma10'].rank()
            df['rank_close_vwap'] = df.groupby('trade_date')['close'].rank() - df.groupby('trade_date')['vwap'].rank()
            df['alpha005'] = df['rank_open_vwap'] * (-1 * abs(df['rank_close_vwap']))
            
            print(f"✅ 成功计算 {len(df)} 条Alpha因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算Alpha因子失败: {e}")
            return None
    
    def calculate_quality_factors(self, ts_code=None, end_date=None):
        """计算质量因子 - 基于财务数据质量"""
        print("\n💎 计算质量因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"i.ts_code = '{ts_code}'")
        if end_date:
            where_conditions.append(f"i.end_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            i.ts_code,
            i.end_date,
            i.revenue,
            i.n_income_attr_p as net_income,
            i.operate_profit,
            i.total_profit,
            i.basic_eps,
            i.ebit,
            i.ebitda,
            
            b.total_assets,
            b.total_liab,
            b.total_hldr_eqy_inc_min_int as total_equity,
            b.money_cap,
            b.accounts_receiv,
            b.inventories,
            b.fix_assets,
            b.goodwill,
            
            c.n_cashflow_act as operating_cf,
            c.n_cashflow_inv_act as investing_cf,
            c.n_cash_flows_fnc_act as financing_cf,
            c.free_cashflow,
            
            -- 获取同期上年数据
            LAG(i.revenue, 4) OVER (PARTITION BY i.ts_code ORDER BY i.end_date) as revenue_ly,
            LAG(i.n_income_attr_p, 4) OVER (PARTITION BY i.ts_code ORDER BY i.end_date) as net_income_ly,
            LAG(b.total_assets, 4) OVER (PARTITION BY i.ts_code ORDER BY i.end_date) as total_assets_ly,
            LAG(b.total_equity, 4) OVER (PARTITION BY i.ts_code ORDER BY i.end_date) as total_equity_ly
            
        FROM stock_income_statement i
        LEFT JOIN stock_balance_sheet b ON i.ts_code = b.ts_code AND i.end_date = b.end_date
        LEFT JOIN stock_cash_flow c ON i.ts_code = c.ts_code AND i.end_date = c.end_date
        WHERE {where_clause}
        ORDER BY i.ts_code, i.end_date
        """
        
        try:
            df = pd.read_sql(query, self.connection)
            
            # 盈利质量因子
            df['earnings_quality'] = df['operating_cf'] / df['net_income']  # 经营现金流/净利润
            df['accruals'] = (df['net_income'] - df['operating_cf']) / df['total_assets']  # 应计项目
            
            # 盈利稳定性
            df['roe'] = df['net_income'] / df['total_equity']
            df['roa'] = df['net_income'] / df['total_assets']
            df['roe_stability'] = df.groupby('ts_code')['roe'].rolling(8).std().reset_index(0, drop=True)
            df['roa_stability'] = df.groupby('ts_code')['roa'].rolling(8).std().reset_index(0, drop=True)
            
            # 增长质量
            df['revenue_growth'] = (df['revenue'] / df['revenue_ly'] - 1) * 100
            df['earnings_growth'] = (df['net_income'] / df['net_income_ly'] - 1) * 100
            df['sustainable_growth'] = df['roe'] * (1 - 0.3)  # 假设分红率30%
            
            # 资产质量
            df['asset_turnover'] = df['revenue'] / df['total_assets']
            df['receivables_turnover'] = df['revenue'] / df['accounts_receiv']
            df['inventory_turnover'] = df['revenue'] / df['inventories']
            df['goodwill_ratio'] = df['goodwill'] / df['total_assets']
            
            # 财务杠杆质量
            df['debt_to_equity'] = df['total_liab'] / df['total_equity']
            df['interest_coverage'] = df['ebit'] / (df['total_liab'] * 0.05)  # 假设利率5%
            
            # 现金流质量
            df['fcf_yield'] = df['free_cashflow'] / df['total_assets']
            df['capex_intensity'] = abs(df['investing_cf']) / df['revenue']
            
            # 综合质量评分
            quality_factors = ['earnings_quality', 'asset_turnover', 'receivables_turnover', 
                             'inventory_turnover', 'fcf_yield']
            
            # 标准化各因子并计算综合评分
            for factor in quality_factors:
                df[f'{factor}_rank'] = df.groupby('end_date')[factor].rank(pct=True)
            
            df['quality_score'] = df[[f'{factor}_rank' for factor in quality_factors]].mean(axis=1)
            
            print(f"✅ 成功计算 {len(df)} 条质量因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算质量因子失败: {e}")
            return None
    
    def calculate_sentiment_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算情绪因子 - 基于资金流和交易行为"""
        print("\n😊 计算情绪因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"m.ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"m.trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"m.trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            m.ts_code,
            m.trade_date,
            m.buy_sm_amount,
            m.sell_sm_amount,
            m.buy_md_amount,
            m.sell_md_amount,
            m.buy_lg_amount,
            m.sell_lg_amount,
            m.buy_elg_amount,
            m.sell_elg_amount,
            m.net_mf_amount,
            
            h.close,
            h.high,
            h.low,
            h.vol,
            h.pct_chg,
            
            d.turnover_rate,
            d.volume_ratio,
            d.pe,
            d.pb,
            
            c.his_low,
            c.his_high,
            c.winner_rate,
            c.cost_50pct,
            
            -- 获取历史数据
            LAG(m.net_mf_amount, 1) OVER (PARTITION BY m.ts_code ORDER BY m.trade_date) as prev_net_mf,
            LAG(h.close, 1) OVER (PARTITION BY m.ts_code ORDER BY m.trade_date) as prev_close,
            LAG(d.turnover_rate, 1) OVER (PARTITION BY m.ts_code ORDER BY m.trade_date) as prev_turnover
            
        FROM stock_moneyflow m
        LEFT JOIN stock_daily_history h ON m.ts_code = h.ts_code AND m.trade_date = h.trade_date
        LEFT JOIN stock_daily_basic d ON m.ts_code = d.ts_code AND m.trade_date = d.trade_date
        LEFT JOIN stock_cyq_perf c ON m.ts_code = c.ts_code AND m.trade_date = c.trade_date
        WHERE {where_clause}
        ORDER BY m.ts_code, m.trade_date
        """
        
        try:
            df = pd.read_sql(query, self.connection)
            
            # 资金流情绪
            df['total_inflow'] = df['buy_sm_amount'] + df['buy_md_amount'] + df['buy_lg_amount'] + df['buy_elg_amount']
            df['total_outflow'] = df['sell_sm_amount'] + df['sell_md_amount'] + df['sell_lg_amount'] + df['sell_elg_amount']
            
            # 主力资金情绪
            df['main_inflow'] = df['buy_lg_amount'] + df['buy_elg_amount']
            df['main_outflow'] = df['sell_lg_amount'] + df['sell_elg_amount']
            df['main_sentiment'] = (df['main_inflow'] - df['main_outflow']) / (df['main_inflow'] + df['main_outflow'])
            
            # 散户资金情绪
            df['retail_inflow'] = df['buy_sm_amount']
            df['retail_outflow'] = df['sell_sm_amount']
            df['retail_sentiment'] = (df['retail_inflow'] - df['retail_outflow']) / (df['retail_inflow'] + df['retail_outflow'])
            
            # 资金流动量情绪
            df['money_flow_momentum'] = df.groupby('ts_code')['net_mf_amount'].rolling(5).mean().reset_index(0, drop=True)
            df['money_flow_acceleration'] = df.groupby('ts_code')['net_mf_amount'].diff().reset_index(0, drop=True)
            
            # 交易活跃度情绪
            df['volume_sentiment'] = df['vol'] / df.groupby('ts_code')['vol'].rolling(20).mean().reset_index(0, drop=True)
            df['turnover_sentiment'] = df['turnover_rate'] / df.groupby('ts_code')['turnover_rate'].rolling(20).mean().reset_index(0, drop=True)
            
            # 价格位置情绪
            df['price_position'] = (df['close'] - df['his_low']) / (df['his_high'] - df['his_low'])
            df['winner_sentiment'] = df['winner_rate'] / 100  # 胜率作为情绪指标
            
            # 技术面情绪
            df['price_momentum'] = df['pct_chg'] / 100
            df['price_momentum_ma'] = df.groupby('ts_code')['price_momentum'].rolling(5).mean().reset_index(0, drop=True)
            
            # 估值情绪
            df['pe_sentiment'] = 1 / (1 + df['pe'] / df.groupby('trade_date')['pe'].median())  # PE相对中位数
            df['pb_sentiment'] = 1 / (1 + df['pb'] / df.groupby('trade_date')['pb'].median())  # PB相对中位数
            
            # 综合情绪指数
            sentiment_factors = ['main_sentiment', 'retail_sentiment', 'volume_sentiment', 
                               'turnover_sentiment', 'price_position', 'winner_sentiment']
            
            # 标准化并计算综合情绪
            for factor in sentiment_factors:
                df[f'{factor}_norm'] = (df[factor] - df[factor].mean()) / df[factor].std()
            
            df['composite_sentiment'] = df[[f'{factor}_norm' for factor in sentiment_factors]].mean(axis=1)
            
            # 情绪极值检测
            df['sentiment_extreme'] = np.where(
                (df['composite_sentiment'] > df['composite_sentiment'].quantile(0.9)) |
                (df['composite_sentiment'] < df['composite_sentiment'].quantile(0.1)), 1, 0
            )
            
            print(f"✅ 成功计算 {len(df)} 条情绪因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算情绪因子失败: {e}")
            return None
    
    def calculate_risk_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算风险因子"""
        print("\n⚠️ 计算风险因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"h.ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"h.trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"h.trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            h.ts_code,
            h.trade_date,
            h.close,
            h.high,
            h.low,
            h.vol,
            h.pct_chg,
            
            d.pe,
            d.pb,
            d.total_mv,
            d.circ_mv,
            
            -- 获取历史数据用于计算波动率
            LAG(h.close, 1) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as prev_close,
            LAG(h.close, 5) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as close_5d,
            LAG(h.close, 20) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as close_20d,
            LAG(h.close, 60) OVER (PARTITION BY h.ts_code ORDER BY h.trade_date) as close_60d
            
        FROM stock_daily_history h
        LEFT JOIN stock_daily_basic d ON h.ts_code = d.ts_code AND h.trade_date = d.trade_date
        WHERE {where_clause}
        ORDER BY h.ts_code, h.trade_date
        """
        
        try:
            df = pd.read_sql(query, self.connection)
            
            # 价格波动率风险
            df['returns'] = df['pct_chg'] / 100
            df['volatility_5d'] = df.groupby('ts_code')['returns'].rolling(5).std().reset_index(0, drop=True) * np.sqrt(252)
            df['volatility_20d'] = df.groupby('ts_code')['returns'].rolling(20).std().reset_index(0, drop=True) * np.sqrt(252)
            df['volatility_60d'] = df.groupby('ts_code')['returns'].rolling(60).std().reset_index(0, drop=True) * np.sqrt(252)
            
            # 下行风险
            df['negative_returns'] = np.where(df['returns'] < 0, df['returns'], 0)
            df['downside_risk'] = df.groupby('ts_code')['negative_returns'].rolling(20).std().reset_index(0, drop=True) * np.sqrt(252)
            
            # 最大回撤
            df['cumulative_returns'] = df.groupby('ts_code')['returns'].cumsum()
            df['running_max'] = df.groupby('ts_code')['cumulative_returns'].expanding().max().reset_index(0, drop=True)
            df['drawdown'] = df['cumulative_returns'] - df['running_max']
            df['max_drawdown_20d'] = df.groupby('ts_code')['drawdown'].rolling(20).min().reset_index(0, drop=True)
            
            # VaR (Value at Risk)
            df['var_5pct'] = df.groupby('ts_code')['returns'].rolling(20).quantile(0.05).reset_index(0, drop=True)
            df['var_1pct'] = df.groupby('ts_code')['returns'].rolling(20).quantile(0.01).reset_index(0, drop=True)
            
            # 流动性风险
            df['volume_volatility'] = df.groupby('ts_code')['vol'].rolling(20).std().reset_index(0, drop=True)
            df['liquidity_risk'] = df['volume_volatility'] / df.groupby('ts_code')['vol'].rolling(20).mean().reset_index(0, drop=True)
            
            # 跳跃风险
            df['price_jump'] = abs(df['returns']) > (2 * df['volatility_20d'] / np.sqrt(252))
            df['jump_frequency'] = df.groupby('ts_code')['price_jump'].rolling(20).sum().reset_index(0, drop=True)
            
            # 尾部风险
            df['skewness'] = df.groupby('ts_code')['returns'].rolling(60).skew().reset_index(0, drop=True)
            df['kurtosis'] = df.groupby('ts_code')['returns'].rolling(60).apply(lambda x: x.kurtosis()).reset_index(0, drop=True)
            
            # 市值风险
            df['size_risk'] = np.log(df['total_mv'])  # 小市值风险
            
            # 估值风险
            df['valuation_risk'] = df['pe'] / df.groupby('trade_date')['pe'].median()  # PE相对风险
            
            # Beta风险 (需要市场指数数据，这里用简化计算)
            market_returns = df.groupby('trade_date')['returns'].mean()  # 简化的市场收益
            df['market_returns'] = df['trade_date'].map(market_returns)
            
            def calculate_beta(group):
                if len(group) >= 20:
                    covariance = np.cov(group['returns'], group['market_returns'])[0, 1]
                    market_variance = np.var(group['market_returns'])
                    return covariance / market_variance if market_variance != 0 else 1
                return 1
            
            df['beta'] = df.groupby('ts_code').rolling(60).apply(calculate_beta).reset_index(0, drop=True)
            
            # 综合风险评分
            risk_factors = ['volatility_20d', 'downside_risk', 'max_drawdown_20d', 
                          'liquidity_risk', 'jump_frequency']
            
            # 标准化风险因子
            for factor in risk_factors:
                df[f'{factor}_rank'] = df.groupby('trade_date')[factor].rank(pct=True)
            
            df['risk_score'] = df[[f'{factor}_rank' for factor in risk_factors]].mean(axis=1)
            
            print(f"✅ 成功计算 {len(df)} 条风险因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算风险因子失败: {e}")
            return None
    
    def calculate_macro_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算宏观因子 - 基于行业和市场环境"""
        print("\n🌍 计算宏观因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"h.ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"h.trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"h.trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            h.ts_code,
            h.trade_date,
            h.close,
            h.pct_chg,
            h.vol,
            
            b.industry,
            b.area,
            
            d.total_mv,
            d.circ_mv,
            d.pe,
            d.pb
            
        FROM stock_daily_history h
        LEFT JOIN stock_basic b ON h.ts_code = b.ts_code
        LEFT JOIN stock_daily_basic d ON h.ts_code = d.ts_code AND h.trade_date = d.trade_date
        WHERE {where_clause}
        ORDER BY h.ts_code, h.trade_date
        """
        
        try:
            df = pd.read_sql(query, self.connection)
            
            # 行业相对表现
            df['returns'] = df['pct_chg'] / 100
            industry_returns = df.groupby(['trade_date', 'industry'])['returns'].mean().reset_index()
            industry_returns.columns = ['trade_date', 'industry', 'industry_returns']
            df = df.merge(industry_returns, on=['trade_date', 'industry'], how='left')
            df['industry_relative_return'] = df['returns'] - df['industry_returns']
            
            # 市场相对表现
            market_returns = df.groupby('trade_date')['returns'].mean().reset_index()
            market_returns.columns = ['trade_date', 'market_returns']
            df = df.merge(market_returns, on='trade_date', how='left')
            df['market_relative_return'] = df['returns'] - df['market_returns']
            
            # 行业动量
            df['industry_momentum'] = df.groupby(['ts_code'])['industry_relative_return'].rolling(20).mean().reset_index(0, drop=True)
            
            # 市值效应
            df['size_factor'] = df.groupby('trade_date')['total_mv'].rank(pct=True)
            
            # 价值效应
            df['value_factor'] = 1 / df.groupby('trade_date')['pe'].rank(pct=True)  # PE倒数排名
            df['book_to_market'] = 1 / df['pb']
            df['value_factor_pb'] = df.groupby('trade_date')['book_to_market'].rank(pct=True)
            
            # 地域效应
            area_returns = df.groupby(['trade_date', 'area'])['returns'].mean().reset_index()
            area_returns.columns = ['trade_date', 'area', 'area_returns']
            df = df.merge(area_returns, on=['trade_date', 'area'], how='left')
            df['area_relative_return'] = df['returns'] - df['area_returns']
            
            # 流动性效应
            df['liquidity_factor'] = df.groupby('trade_date')['vol'].rank(pct=True)
            
            # 市场情绪
            df['market_sentiment'] = df.groupby('trade_date')['returns'].apply(
                lambda x: (x > 0).sum() / len(x)
            ).reset_index(drop=True)
            
            # 波动率聚类
            df['volatility'] = df.groupby('ts_code')['returns'].rolling(20).std().reset_index(0, drop=True)
            df['market_volatility'] = df.groupby('trade_date')['volatility'].mean()
            df['volatility_regime'] = np.where(
                df['market_volatility'] > df['market_volatility'].rolling(60).mean(), 1, 0
            )
            
            print(f"✅ 成功计算 {len(df)} 条宏观因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算宏观因子失败: {e}")
            return None
    
    def generate_factor_report(self, ts_code, start_date, end_date):
        """生成综合因子报告"""
        print(f"\n📊 生成股票 {ts_code} 的综合因子报告")
        print(f"📅 时间范围: {start_date} 至 {end_date}")
        print("=" * 80)
        
        # 计算各类因子
        alpha_factors = self.calculate_alpha_factors(ts_code, start_date, end_date)
        sentiment_factors = self.calculate_sentiment_factors(ts_code, start_date, end_date)
        risk_factors = self.calculate_risk_factors(ts_code, start_date, end_date)
        macro_factors = self.calculate_macro_factors(ts_code, start_date, end_date)
        
        # 合并所有因子数据
        all_factors = None
        
        if alpha_factors is not None and not alpha_factors.empty:
            all_factors = alpha_factors[['ts_code', 'trade_date', 'alpha001', 'alpha002', 'alpha003', 'alpha004', 'alpha005']]
        
        if sentiment_factors is not None and not sentiment_factors.empty:
            sentiment_cols = ['ts_code', 'trade_date', 'main_sentiment', 'retail_sentiment', 'composite_sentiment']
            if all_factors is None:
                all_factors = sentiment_factors[sentiment_cols]
            else:
                all_factors = all_factors.merge(
                    sentiment_factors[sentiment_cols], 
                    on=['ts_code', 'trade_date'], 
                    how='outer'
                )
        
        if risk_factors is not None and not risk_factors.empty:
            risk_cols = ['ts_code', 'trade_date', 'volatility_20d', 'downside_risk', 'risk_score']
            if all_factors is None:
                all_factors = risk_factors[risk_cols]
            else:
                all_factors = all_factors.merge(
                    risk_factors[risk_cols], 
                    on=['ts_code', 'trade_date'], 
                    how='outer'
                )
        
        if macro_factors is not None and not macro_factors.empty:
            macro_cols = ['ts_code', 'trade_date', 'industry_relative_return', 'market_relative_return', 'size_factor', 'value_factor']
            if all_factors is None:
                all_factors = macro_factors[macro_cols]
            else:
                all_factors = all_factors.merge(
                    macro_factors[macro_cols], 
                    on=['ts_code', 'trade_date'], 
                    how='outer'
                )
        
        if all_factors is not None and not all_factors.empty:
            print("\n📈 因子数据概览:")
            print(all_factors.describe())
            
            print("\n📊 最新因子值:")
            latest_data = all_factors.sort_values('trade_date').tail(1)
            for col in all_factors.columns:
                if col not in ['ts_code', 'trade_date']:
                    value = latest_data[col].iloc[0] if not latest_data[col].isna().iloc[0] else 'N/A'
                    print(f"{col}: {value}")
            
            return all_factors
        else:
            print("❌ 未能生成因子数据")
            return None

def main():
    """主函数 - 演示高级因子计算"""
    print("🚀 高级自定义因子库演示")
    print("=" * 60)
    
    # 初始化因子库
    factor_lib = AdvancedFactorLibrary()
    
    try:
        # 设置测试参数
        sample_stock = "000001.SZ"  # 平安银行
        start_date = "2023-01-01"
        end_date = "2024-01-31"
        
        print(f"📊 分析股票: {sample_stock}")
        print(f"📅 时间范围: {start_date} 至 {end_date}")
        
        # 生成综合因子报告
        factor_report = factor_lib.generate_factor_report(sample_stock, start_date, end_date)
        
        if factor_report is not None:
            print("\n✅ 因子计算完成!")
            print("\n💡 使用建议:")
            print("1. Alpha因子可用于选股和择时")
            print("2. 质量因子帮助识别优质公司")
            print("3. 情绪因子捕捉市场情绪变化")
            print("4. 风险因子用于风险管理")
            print("5. 宏观因子分析市场环境影响")
        
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        
    finally:
        factor_lib.close()

if __name__ == "__main__":
    main() 