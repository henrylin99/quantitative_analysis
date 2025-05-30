import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import re
from scipy import stats
from loguru import logger

from app.extensions import db
from app.models import (
    FactorDefinition, FactorValues, StockDailyHistory, StockDailyBasic,
    StockFactor, StockMoneyflow, StockCyqPerf, StockIncomeStatement,
    StockBalanceSheet
)


class FactorEngine:
    """因子计算引擎"""
    
    def __init__(self):
        self.factor_definitions = {}
        self.builtin_factors = {}
        self._init_builtin_factors()
        self.load_factor_definitions()
    
    def _init_builtin_factors(self):
        """初始化内置因子"""
        self.builtin_factors = {
            # 技术面因子
            'momentum_1d': self._momentum_factor,
            'momentum_5d': self._momentum_factor,
            'momentum_20d': self._momentum_factor,
            'volatility_20d': self._volatility_factor,
            'volume_ratio_20d': self._volume_ratio_factor,
            'price_to_ma20': self._price_to_ma_factor,
            
            # 基本面因子
            'pe_percentile': self._pe_percentile_factor,
            'pb_percentile': self._pb_percentile_factor,
            'ps_percentile': self._ps_percentile_factor,
            'roe_ttm': self._roe_factor,
            'roa_ttm': self._roa_factor,
            'revenue_growth': self._revenue_growth_factor,
            'profit_growth': self._profit_growth_factor,
            
            # 资金面因子
            'money_flow_strength': self._money_flow_strength_factor,
            'big_order_ratio': self._big_order_ratio_factor,
            'money_flow_momentum': self._money_flow_momentum_factor,
            
            # 筹码面因子
            'chip_concentration': self._chip_concentration_factor,
            'winner_rate_change': self._winner_rate_change_factor,
        }
    
    def load_factor_definitions(self):
        """加载因子定义"""
        try:
            definitions = FactorDefinition.query.filter_by(is_active=True).all()
            for definition in definitions:
                self.factor_definitions[definition.factor_id] = definition
            logger.info(f"加载了 {len(self.factor_definitions)} 个自定义因子定义")
        except Exception as e:
            logger.error(f"加载因子定义失败: {e}")
    
    def register_factor(self, factor_id: str, factor_name: str, formula: str, 
                       factor_type: str, description: str = None, params: dict = None):
        """注册自定义因子"""
        try:
            # 检查因子是否已存在
            existing = FactorDefinition.query.filter_by(factor_id=factor_id).first()
            if existing:
                # 更新现有因子
                existing.factor_name = factor_name
                existing.factor_formula = formula
                existing.factor_type = factor_type
                existing.description = description
                existing.params = params
                existing.updated_at = datetime.utcnow()
            else:
                # 创建新因子
                new_factor = FactorDefinition(
                    factor_id=factor_id,
                    factor_name=factor_name,
                    factor_formula=formula,
                    factor_type=factor_type,
                    description=description,
                    params=params
                )
                db.session.add(new_factor)
            
            db.session.commit()
            self.load_factor_definitions()  # 重新加载
            logger.info(f"成功注册因子: {factor_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"注册因子失败: {factor_id}, 错误: {e}")
            return False
    
    def calculate_factor(self, factor_id: str, ts_codes: List[str], 
                        start_date: str, end_date: str) -> pd.DataFrame:
        """计算指定因子值"""
        try:
            result = pd.DataFrame()
            
            # 检查是否为内置因子
            if factor_id in self.builtin_factors:
                result = self._calculate_builtin_factor(factor_id, ts_codes, start_date, end_date)
            
            # 检查是否为自定义因子
            elif factor_id in self.factor_definitions:
                result = self._calculate_custom_factor(factor_id, ts_codes, start_date, end_date)
            
            else:
                logger.warning(f"未找到因子定义: {factor_id}")
                return pd.DataFrame()
            
            # 计算百分位排名和Z分数
            if not result.empty:
                result = self._calculate_factor_stats(result, start_date)
                logger.info(f"成功计算因子 {factor_id}: {len(result)} 条记录")
            
            return result
            
        except Exception as e:
            logger.error(f"计算因子失败: {factor_id}, 错误: {e}")
            return pd.DataFrame()
    
    def _calculate_builtin_factor(self, factor_id: str, ts_codes: List[str], 
                                 start_date: str, end_date: str) -> pd.DataFrame:
        """计算内置因子"""
        factor_func = self.builtin_factors[factor_id]
        
        # 根据因子类型获取所需数据
        data = self._get_factor_data(factor_id, ts_codes, start_date, end_date)
        
        # 计算因子值
        result = factor_func(data, factor_id)
        
        return result
    
    def _get_factor_data(self, factor_id: str, ts_codes: List[str], 
                        start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """获取计算因子所需的数据"""
        data = {}
        
        # 扩展日期范围以获取足够的历史数据
        extended_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=252)).strftime('%Y-%m-%d')
        
        try:
            # 基础行情数据
            if any(x in factor_id for x in ['momentum', 'volatility', 'volume', 'price']):
                history_query = StockDailyHistory.query.filter(
                    StockDailyHistory.ts_code.in_(ts_codes),
                    StockDailyHistory.trade_date >= extended_start,
                    StockDailyHistory.trade_date <= end_date
                ).order_by(StockDailyHistory.ts_code, StockDailyHistory.trade_date)
                
                history_data = pd.read_sql(history_query.statement, db.engine)
                data['history'] = history_data
                logger.info(f"获取历史数据: {len(history_data)} 条记录")
            
            # 基本面数据
            if any(x in factor_id for x in ['pe', 'pb', 'ps']):
                basic_query = StockDailyBasic.query.filter(
                    StockDailyBasic.ts_code.in_(ts_codes),
                    StockDailyBasic.trade_date >= start_date,
                    StockDailyBasic.trade_date <= end_date
                ).order_by(StockDailyBasic.ts_code, StockDailyBasic.trade_date)
                
                basic_data = pd.read_sql(basic_query.statement, db.engine)
                data['basic'] = basic_data
            
            # 技术因子数据
            if 'ma' in factor_id:
                factor_query = StockFactor.query.filter(
                    StockFactor.ts_code.in_(ts_codes),
                    StockFactor.trade_date >= start_date,
                    StockFactor.trade_date <= end_date
                ).order_by(StockFactor.ts_code, StockFactor.trade_date)
                
                factor_data = pd.read_sql(factor_query.statement, db.engine)
                data['factor'] = factor_data
            
            # 资金流向数据
            if 'money' in factor_id:
                money_query = StockMoneyflow.query.filter(
                    StockMoneyflow.ts_code.in_(ts_codes),
                    StockMoneyflow.trade_date >= extended_start,
                    StockMoneyflow.trade_date <= end_date
                ).order_by(StockMoneyflow.ts_code, StockMoneyflow.trade_date)
                
                money_data = pd.read_sql(money_query.statement, db.engine)
                data['moneyflow'] = money_data
            
            # 筹码数据
            if 'chip' in factor_id or 'winner' in factor_id:
                cyq_query = StockCyqPerf.query.filter(
                    StockCyqPerf.ts_code.in_(ts_codes),
                    StockCyqPerf.trade_date >= extended_start,
                    StockCyqPerf.trade_date <= end_date
                ).order_by(StockCyqPerf.ts_code, StockCyqPerf.trade_date)
                
                cyq_data = pd.read_sql(cyq_query.statement, db.engine)
                data['cyq'] = cyq_data
            
            # 财务数据
            if any(x in factor_id for x in ['roe', 'roa', 'revenue', 'profit']):
                # 获取最近4个季度的财务数据
                income_query = StockIncomeStatement.query.filter(
                    StockIncomeStatement.ts_code.in_(ts_codes)
                ).order_by(StockIncomeStatement.ts_code, StockIncomeStatement.end_date.desc())
                
                income_data = pd.read_sql(income_query.statement, db.engine)
                data['income'] = income_data
                
                balance_query = StockBalanceSheet.query.filter(
                    StockBalanceSheet.ts_code.in_(ts_codes)
                ).order_by(StockBalanceSheet.ts_code, StockBalanceSheet.end_date.desc())
                
                balance_data = pd.read_sql(balance_query.statement, db.engine)
                data['balance'] = balance_data
            
        except Exception as e:
            logger.error(f"获取因子数据失败: {e}")
        
        return data
    
    # ==================== 内置因子计算函数 ====================
    
    def _momentum_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """动量因子：计算N日收益率"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        # 提取周期参数
        period = int(factor_id.split('_')[1].replace('d', ''))
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data[f'return_{period}d'] = stock_data['close'].pct_change(period)
            
            # 只保留指定日期范围的数据
            result_list.append(stock_data[['ts_code', 'trade_date', f'return_{period}d']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={f'return_{period}d': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _volatility_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """波动率因子：计算N日收益率标准差"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        period = int(factor_id.split('_')[1].replace('d', ''))
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data['daily_return'] = stock_data['close'].pct_change()
            stock_data[f'volatility_{period}d'] = stock_data['daily_return'].rolling(period).std()
            
            result_list.append(stock_data[['ts_code', 'trade_date', f'volatility_{period}d']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={f'volatility_{period}d': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _volume_ratio_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """成交量比率因子"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        period = int(factor_id.split('_')[2].replace('d', ''))
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data['vol_ma'] = stock_data['vol'].rolling(period).mean()
            stock_data['volume_ratio'] = stock_data['vol'] / stock_data['vol_ma']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'volume_ratio']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'volume_ratio': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _price_to_ma_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """价格相对均线因子"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        period = int(factor_id.split('ma')[1])
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data[f'ma{period}'] = stock_data['close'].rolling(period).mean()
            stock_data['price_to_ma'] = stock_data['close'] / stock_data[f'ma{period}'] - 1
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'price_to_ma']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'price_to_ma': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _pe_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PE历史分位数因子"""
        if 'basic' not in data or data['basic'].empty:
            return pd.DataFrame()
        
        df = data['basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data = stock_data[stock_data['pe_ttm'].notna() & (stock_data['pe_ttm'] > 0)]
            
            if len(stock_data) > 20:  # 至少需要20个数据点
                stock_data['pe_percentile'] = stock_data['pe_ttm'].rolling(252, min_periods=20).apply(
                    lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
                )
                result_list.append(stock_data[['ts_code', 'trade_date', 'pe_percentile']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'pe_percentile': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _pb_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PB历史分位数因子"""
        if 'basic' not in data or data['basic'].empty:
            return pd.DataFrame()
        
        df = data['basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data = stock_data[stock_data['pb'].notna() & (stock_data['pb'] > 0)]
            
            if len(stock_data) > 20:
                stock_data['pb_percentile'] = stock_data['pb'].rolling(252, min_periods=20).apply(
                    lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
                )
                result_list.append(stock_data[['ts_code', 'trade_date', 'pb_percentile']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'pb_percentile': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _ps_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PS历史分位数因子"""
        if 'basic' not in data or data['basic'].empty:
            return pd.DataFrame()
        
        df = data['basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data = stock_data[stock_data['ps_ttm'].notna() & (stock_data['ps_ttm'] > 0)]
            
            if len(stock_data) > 20:
                stock_data['ps_percentile'] = stock_data['ps_ttm'].rolling(252, min_periods=20).apply(
                    lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
                )
                result_list.append(stock_data[['ts_code', 'trade_date', 'ps_percentile']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'ps_percentile': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _roe_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """ROE因子（TTM）"""
        if 'income' not in data or 'balance' not in data:
            return pd.DataFrame()
        
        income_df = data['income'].copy()
        balance_df = data['balance'].copy()
        
        # 计算TTM净利润和平均净资产
        result_list = []
        for ts_code in income_df['ts_code'].unique():
            stock_income = income_df[income_df['ts_code'] == ts_code].sort_values('end_date', ascending=False)
            stock_balance = balance_df[balance_df['ts_code'] == ts_code].sort_values('end_date', ascending=False)
            
            if len(stock_income) >= 4 and len(stock_balance) >= 2:
                # 计算TTM净利润
                ttm_profit = stock_income.head(4)['n_income_attr_p'].sum()
                
                # 计算平均净资产
                avg_equity = stock_balance.head(2)['total_hldr_eqy_exc_min_int'].mean()
                
                if avg_equity and avg_equity > 0:
                    roe_ttm = ttm_profit / avg_equity
                    
                    # 使用最新报告期对应的交易日期
                    latest_date = stock_income.iloc[0]['end_date']
                    
                    result_list.append({
                        'ts_code': ts_code,
                        'trade_date': latest_date,
                        'factor_value': roe_ttm
                    })
        
        if result_list:
            result = pd.DataFrame(result_list)
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']]
        
        return pd.DataFrame()
    
    def _roa_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """ROA因子（TTM）"""
        if 'income' not in data or 'balance' not in data:
            return pd.DataFrame()
        
        income_df = data['income'].copy()
        balance_df = data['balance'].copy()
        
        result_list = []
        for ts_code in income_df['ts_code'].unique():
            stock_income = income_df[income_df['ts_code'] == ts_code].sort_values('end_date', ascending=False)
            stock_balance = balance_df[balance_df['ts_code'] == ts_code].sort_values('end_date', ascending=False)
            
            if len(stock_income) >= 4 and len(stock_balance) >= 2:
                # 计算TTM净利润
                ttm_profit = stock_income.head(4)['n_income_attr_p'].sum()
                
                # 计算平均总资产
                avg_assets = stock_balance.head(2)['total_assets'].mean()
                
                if avg_assets and avg_assets > 0:
                    roa_ttm = ttm_profit / avg_assets
                    
                    latest_date = stock_income.iloc[0]['end_date']
                    
                    result_list.append({
                        'ts_code': ts_code,
                        'trade_date': latest_date,
                        'factor_value': roa_ttm
                    })
        
        if result_list:
            result = pd.DataFrame(result_list)
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']]
        
        return pd.DataFrame()
    
    def _revenue_growth_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """营收增长率因子"""
        if 'income' not in data:
            return pd.DataFrame()
        
        income_df = data['income'].copy()
        
        result_list = []
        for ts_code in income_df['ts_code'].unique():
            stock_data = income_df[income_df['ts_code'] == ts_code].sort_values('end_date', ascending=False)
            
            if len(stock_data) >= 8:  # 至少需要2年数据
                # 计算最近4个季度和去年同期4个季度的营收
                current_ttm = stock_data.head(4)['revenue'].sum()
                previous_ttm = stock_data.iloc[4:8]['revenue'].sum()
                
                if previous_ttm and previous_ttm > 0:
                    revenue_growth = (current_ttm - previous_ttm) / previous_ttm
                    
                    latest_date = stock_data.iloc[0]['end_date']
                    
                    result_list.append({
                        'ts_code': ts_code,
                        'trade_date': latest_date,
                        'factor_value': revenue_growth
                    })
        
        if result_list:
            result = pd.DataFrame(result_list)
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']]
        
        return pd.DataFrame()
    
    def _profit_growth_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """利润增长率因子"""
        if 'income' not in data:
            return pd.DataFrame()
        
        income_df = data['income'].copy()
        
        result_list = []
        for ts_code in income_df['ts_code'].unique():
            stock_data = income_df[income_df['ts_code'] == ts_code].sort_values('end_date', ascending=False)
            
            if len(stock_data) >= 8:
                current_ttm = stock_data.head(4)['n_income_attr_p'].sum()
                previous_ttm = stock_data.iloc[4:8]['n_income_attr_p'].sum()
                
                if previous_ttm and previous_ttm > 0:
                    profit_growth = (current_ttm - previous_ttm) / previous_ttm
                    
                    latest_date = stock_data.iloc[0]['end_date']
                    
                    result_list.append({
                        'ts_code': ts_code,
                        'trade_date': latest_date,
                        'factor_value': profit_growth
                    })
        
        if result_list:
            result = pd.DataFrame(result_list)
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']]
        
        return pd.DataFrame()
    
    def _money_flow_strength_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """资金流向强度因子"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()
        
        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算大单净流入强度
            stock_data['big_net_amount'] = (stock_data['buy_lg_amount'] + stock_data['buy_elg_amount']) - \
                                         (stock_data['sell_lg_amount'] + stock_data['sell_elg_amount'])
            
            # 计算总成交额
            stock_data['total_amount'] = (stock_data['buy_sm_amount'] + stock_data['buy_md_amount'] + 
                                        stock_data['buy_lg_amount'] + stock_data['buy_elg_amount'])
            
            # 计算资金流向强度
            stock_data['money_flow_strength'] = stock_data['big_net_amount'] / stock_data['total_amount']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'money_flow_strength']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'money_flow_strength': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _big_order_ratio_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """大单占比因子"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()
        
        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算大单总额
            stock_data['big_amount'] = stock_data['buy_lg_amount'] + stock_data['sell_lg_amount'] + \
                                     stock_data['buy_elg_amount'] + stock_data['sell_elg_amount']
            
            # 计算总成交额
            stock_data['total_amount'] = (stock_data['buy_sm_amount'] + stock_data['sell_sm_amount'] +
                                        stock_data['buy_md_amount'] + stock_data['sell_md_amount'] +
                                        stock_data['buy_lg_amount'] + stock_data['sell_lg_amount'] +
                                        stock_data['buy_elg_amount'] + stock_data['sell_elg_amount'])
            
            # 计算大单占比
            stock_data['big_order_ratio'] = stock_data['big_amount'] / stock_data['total_amount']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'big_order_ratio']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'big_order_ratio': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _money_flow_momentum_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """资金流向动量因子"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()
        
        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算5日资金流向动量
            stock_data['net_flow_5d'] = stock_data['net_mf_amount'].rolling(5).sum()
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'net_flow_5d']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'net_flow_5d': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _chip_concentration_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """筹码集中度因子"""
        if 'cyq' not in data or data['cyq'].empty:
            return pd.DataFrame()
        
        df = data['cyq'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算筹码集中度：90%筹码的价格区间相对中位数的比例
            stock_data['chip_concentration'] = (stock_data['cost_95pct'] - stock_data['cost_5pct']) / stock_data['cost_50pct']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'chip_concentration']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'chip_concentration': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _winner_rate_change_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """胜率变化因子"""
        if 'cyq' not in data or data['cyq'].empty:
            return pd.DataFrame()
        
        df = data['cyq'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算胜率5日变化
            stock_data['winner_rate_change'] = stock_data['winner_rate'].diff(5)
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'winner_rate_change']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'winner_rate_change': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def calculate_all_factors(self, trade_date: str, ts_codes: List[str] = None) -> pd.DataFrame:
        """计算所有因子的当日值"""
        try:
            if ts_codes is None:
                # 获取所有活跃股票
                from app.models import StockBasic
                stocks = StockBasic.query.all()
                ts_codes = [stock.ts_code for stock in stocks]
            
            all_results = []
            
            # 计算内置因子
            for factor_id in self.builtin_factors.keys():
                try:
                    result = self.calculate_factor(factor_id, ts_codes, trade_date, trade_date)
                    if not result.empty:
                        all_results.append(result)
                except Exception as e:
                    logger.error(f"计算内置因子失败: {factor_id}, 错误: {e}")
            
            # 计算自定义因子
            for factor_id in self.factor_definitions.keys():
                try:
                    result = self.calculate_factor(factor_id, ts_codes, trade_date, trade_date)
                    if not result.empty:
                        all_results.append(result)
                except Exception as e:
                    logger.error(f"计算自定义因子失败: {factor_id}, 错误: {e}")
            
            if all_results:
                final_result = pd.concat(all_results, ignore_index=True)
                
                # 计算百分位排名和Z分数
                final_result = self._calculate_factor_stats(final_result, trade_date)
                
                return final_result
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"计算所有因子失败: {e}")
            return pd.DataFrame()
    
    def _calculate_factor_stats(self, df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
        """计算因子的百分位排名和Z分数"""
        try:
            result_list = []
            
            for factor_id in df['factor_id'].unique():
                factor_data = df[df['factor_id'] == factor_id].copy()
                
                if len(factor_data) > 1:
                    # 计算百分位排名
                    factor_data['percentile_rank'] = factor_data['factor_value'].rank(pct=True) * 100
                    
                    # 计算Z分数
                    mean_val = factor_data['factor_value'].mean()
                    std_val = factor_data['factor_value'].std()
                    if std_val > 0:
                        factor_data['z_score'] = (factor_data['factor_value'] - mean_val) / std_val
                    else:
                        factor_data['z_score'] = 0
                
                result_list.append(factor_data)
            
            if result_list:
                return pd.concat(result_list, ignore_index=True)
            
            return df
            
        except Exception as e:
            logger.error(f"计算因子统计量失败: {e}")
            return df
    
    def save_factor_values(self, df: pd.DataFrame) -> bool:
        """保存因子值到数据库"""
        try:
            if df.empty:
                return True
            
            # 删除已存在的数据
            trade_dates = df['trade_date'].unique()
            factor_ids = df['factor_id'].unique()
            
            for trade_date in trade_dates:
                for factor_id in factor_ids:
                    FactorValues.query.filter_by(
                        trade_date=trade_date,
                        factor_id=factor_id
                    ).delete()
            
            # 批量插入新数据
            records = []
            for _, row in df.iterrows():
                record = FactorValues(
                    ts_code=row['ts_code'],
                    trade_date=row['trade_date'],
                    factor_id=row['factor_id'],
                    factor_value=row['factor_value'],
                    percentile_rank=row.get('percentile_rank'),
                    z_score=row.get('z_score')
                )
                records.append(record)
            
            db.session.bulk_save_objects(records)
            db.session.commit()
            
            logger.info(f"成功保存 {len(records)} 条因子值记录")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"保存因子值失败: {e}")
            return False
    
    def get_factor_exposure(self, factor_id: str, trade_date: str) -> pd.DataFrame:
        """获取因子暴露度"""
        try:
            query = FactorValues.query.filter_by(
                factor_id=factor_id,
                trade_date=trade_date
            ).order_by(FactorValues.z_score.desc())
            
            result = pd.read_sql(query.statement, db.engine)
            return result
            
        except Exception as e:
            logger.error(f"获取因子暴露度失败: {factor_id}, {trade_date}, 错误: {e}")
            return pd.DataFrame()
    
    def _calculate_custom_factor(self, factor_id: str, ts_codes: List[str], 
                                start_date: str, end_date: str) -> pd.DataFrame:
        """计算自定义因子（待实现）"""
        # TODO: 实现自定义因子公式解析和计算
        logger.warning(f"自定义因子计算功能待实现: {factor_id}")
        return pd.DataFrame()
    
    def get_factor_list(self, factor_type: str = None, is_active: bool = True) -> List[Dict[str, Any]]:
        """获取因子列表"""
        try:
            factor_list = []
            
            # 添加内置因子
            for factor_id, func in self.builtin_factors.items():
                # 根据因子ID推断因子类型
                if any(x in factor_id for x in ['momentum', 'volatility', 'volume', 'price', 'ma']):
                    ftype = 'technical'
                elif any(x in factor_id for x in ['pe', 'pb', 'ps', 'roe', 'roa', 'revenue', 'profit']):
                    ftype = 'fundamental'
                elif any(x in factor_id for x in ['money', 'flow']):
                    ftype = 'money_flow'
                elif any(x in factor_id for x in ['chip', 'winner']):
                    ftype = 'chip'
                else:
                    ftype = 'other'
                
                if factor_type is None or ftype == factor_type:
                    factor_list.append({
                        'factor_id': factor_id,
                        'factor_name': factor_id.replace('_', ' ').title(),
                        'factor_type': ftype,
                        'is_builtin': True,
                        'is_active': True,
                        'description': f"内置{ftype}因子"
                    })
            
            # 添加自定义因子
            for factor_id, definition in self.factor_definitions.items():
                if factor_type is None or definition.factor_type == factor_type:
                    if not is_active or definition.is_active:
                        factor_list.append({
                            'factor_id': definition.factor_id,
                            'factor_name': definition.factor_name,
                            'factor_type': definition.factor_type,
                            'is_builtin': False,
                            'is_active': definition.is_active,
                            'description': definition.description,
                            'formula': definition.factor_formula,
                            'params': definition.params,
                            'created_at': definition.created_at.isoformat() if definition.created_at else None,
                            'updated_at': definition.updated_at.isoformat() if definition.updated_at else None
                        })
            
            return factor_list
            
        except Exception as e:
            logger.error(f"获取因子列表失败: {e}")
            return []
    
    def create_factor_definition(self, factor_id: str, factor_name: str, 
                               factor_formula: str, factor_type: str,
                               description: str = None, params: dict = None) -> bool:
        """创建因子定义（别名方法，兼容API调用）"""
        return self.register_factor(factor_id, factor_name, factor_formula, 
                                   factor_type, description, params) 