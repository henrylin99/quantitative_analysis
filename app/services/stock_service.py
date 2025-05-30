from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import and_, or_, desc, asc
from app.extensions import db
from app.models import (
    StockBasic, StockDailyHistory, StockDailyBasic, 
    StockFactor, StockMaData, StockMoneyflow, StockCyqPerf
)
from app.utils.cache import cached
from loguru import logger
import pandas as pd
import numpy as np

class StockService:
    """股票数据服务类"""
    
    @staticmethod
    @cached(expire=1800, key_prefix='stock_basic')
    def get_stock_list(industry=None, area=None, page=1, page_size=20):
        """获取股票列表"""
        try:
            query = StockBasic.query
            
            # 添加筛选条件
            if industry:
                query = query.filter(StockBasic.industry == industry)
            if area:
                query = query.filter(StockBasic.area == area)
            
            # 分页
            offset = (page - 1) * page_size
            stocks = query.offset(offset).limit(page_size).all()
            total = query.count()
            
            return {
                'stocks': [stock.to_dict() for stock in stocks],
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return {'stocks': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0}
    
    @staticmethod
    @cached(expire=600, key_prefix='stock_info')
    def get_stock_info(ts_code: str):
        """获取股票基本信息"""
        try:
            stock = StockBasic.query.filter_by(ts_code=ts_code).first()
            return stock.to_dict() if stock else None
        except Exception as e:
            logger.error(f"获取股票信息失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=300, key_prefix='daily_history')
    def get_daily_history(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 60):
        """获取股票日线历史数据"""
        try:
            query = StockDailyHistory.query.filter_by(ts_code=ts_code)
            
            if start_date:
                query = query.filter(StockDailyHistory.trade_date >= start_date)
            if end_date:
                query = query.filter(StockDailyHistory.trade_date <= end_date)
            
            # 按日期倒序排列，获取最新的数据（最新的在前面）
            history = query.order_by(desc(StockDailyHistory.trade_date)).limit(limit).all()
            
            return [item.to_dict() for item in history]
        except Exception as e:
            logger.error(f"获取日线历史数据失败: {ts_code}, 错误: {e}")
            return []
    
    @staticmethod
    @cached(expire=300, key_prefix='daily_basic')
    def get_daily_basic(ts_code: str, trade_date: str = None):
        """获取股票日线基本数据"""
        try:
            query = StockDailyBasic.query.filter_by(ts_code=ts_code)
            
            if trade_date:
                query = query.filter_by(trade_date=trade_date)
            else:
                # 获取最新数据
                query = query.order_by(desc(StockDailyBasic.trade_date))
            
            basic = query.first()
            return basic.to_dict() if basic else None
        except Exception as e:
            logger.error(f"获取日线基本数据失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=300, key_prefix='stock_factor')
    def get_stock_factors(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 60):
        """获取股票技术因子数据"""
        try:
            # 首先尝试从stock_factor表获取数据
            query = StockFactor.query.filter_by(ts_code=ts_code)
            
            if start_date:
                query = query.filter(StockFactor.trade_date >= start_date)
            if end_date:
                query = query.filter(StockFactor.trade_date <= end_date)
            
            # 按日期倒序排列，获取最新的数据（最新的在前面）
            factors = query.order_by(desc(StockFactor.trade_date)).limit(limit).all()
            
            factor_data = [item.to_dict() for item in factors]
            
            # 如果stock_factor表数据不足，基于历史数据计算技术指标
            if len(factor_data) < limit:
                logger.info(f"stock_factor表数据不足({len(factor_data)}条)，基于历史数据计算技术指标")
                history_data = StockService.get_daily_history(ts_code, start_date, end_date, limit)
                if history_data:
                    calculated_factors = StockService._calculate_technical_indicators(history_data)
                    return calculated_factors
            
            return factor_data
        except Exception as e:
            logger.error(f"获取技术因子数据失败: {ts_code}, 错误: {e}")
            # 如果出错，尝试基于历史数据计算
            try:
                history_data = StockService.get_daily_history(ts_code, start_date, end_date, limit)
                if history_data:
                    return StockService._calculate_technical_indicators(history_data)
            except Exception as calc_error:
                logger.error(f"计算技术指标失败: {calc_error}")
            return []
    
    @staticmethod
    @cached(expire=600, key_prefix='ma_data')
    def get_ma_data(ts_code: str):
        """获取股票均线数据"""
        try:
            ma_data = StockMaData.query.filter_by(ts_code=ts_code).first()
            return ma_data.to_dict() if ma_data else None
        except Exception as e:
            logger.error(f"获取均线数据失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=300, key_prefix='moneyflow')
    def get_moneyflow(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 30):
        """获取股票资金流向数据"""
        try:
            query = StockMoneyflow.query.filter_by(ts_code=ts_code)
            
            if start_date:
                query = query.filter(StockMoneyflow.trade_date >= start_date)
            if end_date:
                query = query.filter(StockMoneyflow.trade_date <= end_date)
            
            moneyflow = query.order_by(desc(StockMoneyflow.trade_date)).limit(limit).all()
            return [item.to_dict() for item in reversed(moneyflow)]
        except Exception as e:
            logger.error(f"获取资金流向数据失败: {ts_code}, 错误: {e}")
            return []
    
    @staticmethod
    @cached(expire=300, key_prefix='cyq_perf')
    def get_cyq_perf(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 30):
        """获取股票筹码分布数据"""
        try:
            query = StockCyqPerf.query.filter_by(ts_code=ts_code)
            
            if start_date:
                query = query.filter(StockCyqPerf.trade_date >= start_date)
            if end_date:
                query = query.filter(StockCyqPerf.trade_date <= end_date)
            
            cyq_perf = query.order_by(desc(StockCyqPerf.trade_date)).limit(limit).all()
            return [item.to_dict() for item in reversed(cyq_perf)]
        except Exception as e:
            logger.error(f"获取筹码分布数据失败: {ts_code}, 错误: {e}")
            return []
    
    @staticmethod
    def get_stock_detail(ts_code: str):
        """获取股票详细信息（综合数据）"""
        try:
            # 获取基本信息
            basic_info = StockService.get_stock_info(ts_code)
            if not basic_info:
                return None
            
            # 获取最新日线数据
            latest_daily = StockService.get_daily_basic(ts_code)
            
            # 获取均线数据
            ma_data = StockService.get_ma_data(ts_code)
            
            # 获取最近的资金流向
            recent_moneyflow = StockService.get_moneyflow(ts_code, limit=1)
            
            # 获取最近的筹码数据
            recent_cyq = StockService.get_cyq_perf(ts_code, limit=1)
            
            return {
                'basic_info': basic_info,
                'latest_daily': latest_daily,
                'ma_data': ma_data,
                'recent_moneyflow': recent_moneyflow[0] if recent_moneyflow else None,
                'recent_cyq': recent_cyq[0] if recent_cyq else None
            }
        except Exception as e:
            logger.error(f"获取股票详细信息失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=1800, key_prefix='industry_list')
    def get_industry_list():
        """获取行业列表"""
        try:
            industries = db.session.query(StockBasic.industry).distinct().filter(
                StockBasic.industry.isnot(None)
            ).all()
            return [industry[0] for industry in industries if industry[0]]
        except Exception as e:
            logger.error(f"获取行业列表失败: {e}")
            return []
    
    @staticmethod
    @cached(expire=1800, key_prefix='area_list')
    def get_area_list():
        """获取地域列表"""
        try:
            areas = db.session.query(StockBasic.area).distinct().filter(
                StockBasic.area.isnot(None)
            ).all()
            return [area[0] for area in areas if area[0]]
        except Exception as e:
            logger.error(f"获取地域列表失败: {e}")
            return []
    
    @staticmethod
    def screen_stocks(criteria: Dict):
        """基于股票业务大宽表的增强筛选"""
        try:
            from app.models import StockBusiness
            from sqlalchemy import and_, or_, text
            from datetime import datetime, timedelta
            
            # 构建基础查询，关联stock_basic表获取行业和地域信息
            query = db.session.query(StockBusiness, StockBasic).join(
                StockBasic, StockBusiness.ts_code == StockBasic.ts_code
            )
            
            # 确定查询日期
            target_date = None
            if criteria.get('trade_date'):
                target_date = datetime.strptime(criteria['trade_date'], '%Y-%m-%d').date()
                query = query.filter(StockBusiness.trade_date == target_date)
            else:
                # 使用最新数据，先获取最新日期
                latest_date = db.session.query(db.func.max(StockBusiness.trade_date)).scalar()
                if latest_date:
                    query = query.filter(StockBusiness.trade_date == latest_date)
            
            # 基本条件筛选
            if criteria.get('industry'):
                query = query.filter(StockBasic.industry == criteria['industry'])
            
            if criteria.get('area'):
                query = query.filter(StockBasic.area == criteria['area'])
            
            if criteria.get('market'):
                market = criteria['market']
                if market == 'SZ':
                    query = query.filter(StockBusiness.ts_code.like('%.SZ'))
                elif market == 'SH':
                    query = query.filter(StockBusiness.ts_code.like('%.SH'))
            
            # 估值指标筛选
            if criteria.get('pe_min'):
                query = query.filter(StockBusiness.pe >= float(criteria['pe_min']))
            if criteria.get('pe_max'):
                query = query.filter(StockBusiness.pe <= float(criteria['pe_max']))
            
            if criteria.get('pb_min'):
                query = query.filter(StockBusiness.pb >= float(criteria['pb_min']))
            if criteria.get('pb_max'):
                query = query.filter(StockBusiness.pb <= float(criteria['pb_max']))
            
            if criteria.get('ps_min'):
                query = query.filter(StockBusiness.ps >= float(criteria['ps_min']))
            if criteria.get('ps_max'):
                query = query.filter(StockBusiness.ps <= float(criteria['ps_max']))
            
            if criteria.get('dv_min'):
                query = query.filter(StockBusiness.dv_ratio >= float(criteria['dv_min']))
            if criteria.get('dv_max'):
                query = query.filter(StockBusiness.dv_ratio <= float(criteria['dv_max']))
            
            # 市值和交易指标筛选
            if criteria.get('mv_min'):
                query = query.filter(StockBusiness.total_mv >= float(criteria['mv_min']))
            if criteria.get('mv_max'):
                query = query.filter(StockBusiness.total_mv <= float(criteria['mv_max']))
            
            if criteria.get('circ_mv_min'):
                query = query.filter(StockBusiness.circ_mv >= float(criteria['circ_mv_min']))
            if criteria.get('circ_mv_max'):
                query = query.filter(StockBusiness.circ_mv <= float(criteria['circ_mv_max']))
            
            if criteria.get('turnover_min'):
                query = query.filter(StockBusiness.turnover_rate >= float(criteria['turnover_min']))
            if criteria.get('turnover_max'):
                query = query.filter(StockBusiness.turnover_rate <= float(criteria['turnover_max']))
            
            if criteria.get('volume_ratio_min'):
                query = query.filter(StockBusiness.volume_ratio >= float(criteria['volume_ratio_min']))
            if criteria.get('volume_ratio_max'):
                query = query.filter(StockBusiness.volume_ratio <= float(criteria['volume_ratio_max']))
            
            # 技术指标筛选
            if criteria.get('rsi6_min'):
                query = query.filter(StockBusiness.factor_rsi_6 >= float(criteria['rsi6_min']))
            if criteria.get('rsi6_max'):
                query = query.filter(StockBusiness.factor_rsi_6 <= float(criteria['rsi6_max']))
            
            if criteria.get('kdj_k_min'):
                query = query.filter(StockBusiness.factor_kdj_k >= float(criteria['kdj_k_min']))
            if criteria.get('kdj_k_max'):
                query = query.filter(StockBusiness.factor_kdj_k <= float(criteria['kdj_k_max']))
            
            if criteria.get('macd_min'):
                query = query.filter(StockBusiness.factor_macd >= float(criteria['macd_min']))
            if criteria.get('macd_max'):
                query = query.filter(StockBusiness.factor_macd <= float(criteria['macd_max']))
            
            if criteria.get('cci_min'):
                query = query.filter(StockBusiness.factor_cci >= float(criteria['cci_min']))
            if criteria.get('cci_max'):
                query = query.filter(StockBusiness.factor_cci <= float(criteria['cci_max']))
            
            # 资金流向筛选
            if criteria.get('net_amount_min'):
                query = query.filter(StockBusiness.moneyflow_net_amount >= float(criteria['net_amount_min']))
            if criteria.get('net_amount_max'):
                query = query.filter(StockBusiness.moneyflow_net_amount <= float(criteria['net_amount_max']))
            
            if criteria.get('lg_buy_rate_min'):
                query = query.filter(StockBusiness.moneyflow_buy_lg_amount_rate >= float(criteria['lg_buy_rate_min']))
            if criteria.get('lg_buy_rate_max'):
                query = query.filter(StockBusiness.moneyflow_buy_lg_amount_rate <= float(criteria['lg_buy_rate_max']))
            
            if criteria.get('net_d5_amount_min'):
                query = query.filter(StockBusiness.moneyflow_net_d5_amount >= float(criteria['net_d5_amount_min']))
            if criteria.get('net_d5_amount_max'):
                query = query.filter(StockBusiness.moneyflow_net_d5_amount <= float(criteria['net_d5_amount_max']))
            
            # 处理动态查询条件
            dynamic_conditions = criteria.get('dynamic_conditions', [])
            for condition in dynamic_conditions:
                field_a = condition.get('field_a')
                operator = condition.get('operator')
                field_b = condition.get('field_b')
                value = condition.get('value')
                
                if not field_a or not operator:
                    continue
                
                # 构建动态条件
                if field_b:
                    # 字段间比较
                    field_a_attr = getattr(StockBusiness, field_a, None)
                    field_b_attr = getattr(StockBusiness, field_b, None)
                    
                    if field_a_attr is not None and field_b_attr is not None:
                        if operator == '>':
                            query = query.filter(field_a_attr > field_b_attr)
                        elif operator == '>=':
                            query = query.filter(field_a_attr >= field_b_attr)
                        elif operator == '<':
                            query = query.filter(field_a_attr < field_b_attr)
                        elif operator == '<=':
                            query = query.filter(field_a_attr <= field_b_attr)
                        elif operator == '=':
                            query = query.filter(field_a_attr == field_b_attr)
                        elif operator == '!=':
                            query = query.filter(field_a_attr != field_b_attr)
                elif value is not None:
                    # 字段与固定值比较
                    field_a_attr = getattr(StockBusiness, field_a, None)
                    
                    if field_a_attr is not None:
                        try:
                            value_float = float(value)
                            if operator == '>':
                                query = query.filter(field_a_attr > value_float)
                            elif operator == '>=':
                                query = query.filter(field_a_attr >= value_float)
                            elif operator == '<':
                                query = query.filter(field_a_attr < value_float)
                            elif operator == '<=':
                                query = query.filter(field_a_attr <= value_float)
                            elif operator == '=':
                                query = query.filter(field_a_attr == value_float)
                            elif operator == '!=':
                                query = query.filter(field_a_attr != value_float)
                        except ValueError:
                            logger.warning(f"动态条件值转换失败: {value}")
                            continue
            
            # 执行查询
            results = query.all()
            
            # 转换为字典列表，合并StockBusiness和StockBasic的数据
            stocks = []
            for stock_business, stock_basic in results:
                stock_dict = stock_business.to_dict()
                # 添加基本信息
                stock_dict.update({
                    'industry': stock_basic.industry,
                    'area': stock_basic.area,
                    'symbol': stock_basic.symbol,
                    'name': stock_basic.name,
                    'list_date': stock_basic.list_date.strftime('%Y-%m-%d') if stock_basic.list_date else None
                })
                stocks.append(stock_dict)
            
            # 限制返回数量，避免数据过多
            max_results = 200
            total_count = len(stocks)
            has_more = total_count > max_results
            
            if has_more:
                stocks = stocks[:max_results]
            
            logger.info(f"股票筛选完成，共找到 {total_count} 只股票，返回 {len(stocks)} 只")
            
            return {
                'stocks': stocks,
                'total': total_count,
                'criteria': criteria,
                'has_more': has_more
            }
            
        except Exception as e:
            logger.error(f"股票筛选失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return {
                'stocks': [],
                'total': 0,
                'criteria': criteria,
                'error': str(e)
            }
    
    @staticmethod
    def _calculate_technical_indicators(history_data: List[Dict]) -> List[Dict]:
        """基于历史数据计算技术指标"""
        try:
            import pandas as pd
            import numpy as np
            
            if not history_data or len(history_data) < 20:
                logger.warning("历史数据不足，无法计算技术指标")
                return []
            
            # 转换为DataFrame
            df = pd.DataFrame(history_data)
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.sort_values('trade_date')
            
            # 计算技术指标
            result = []
            
            for i, row in df.iterrows():
                factor_data = {
                    'ts_code': row['ts_code'],
                    'trade_date': row['trade_date'].strftime('%Y-%m-%d'),
                    'close': row['close'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'vol': row['vol'],
                    'amount': row['amount']
                }
                
                # 获取当前位置之前的数据用于计算指标
                current_data = df.iloc[:i+1]
                
                if len(current_data) >= 12:  # 至少需要12天数据
                    # 计算MACD
                    macd_data = StockService._calculate_macd(current_data['close'])
                    if macd_data:
                        factor_data.update(macd_data)
                    
                    # 计算KDJ
                    kdj_data = StockService._calculate_kdj(current_data)
                    if kdj_data:
                        factor_data.update(kdj_data)
                    
                    # 计算RSI
                    rsi_data = StockService._calculate_rsi(current_data['close'])
                    if rsi_data:
                        factor_data.update(rsi_data)
                    
                    # 计算布林带
                    boll_data = StockService._calculate_bollinger_bands(current_data['close'])
                    if boll_data:
                        factor_data.update(boll_data)
                
                result.append(factor_data)
            
            return result
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return []
    
    @staticmethod
    def _calculate_macd(prices, fast=12, slow=26, signal=9):
        """计算MACD指标"""
        try:
            import pandas as pd
            
            prices = pd.Series(prices)
            
            # 计算EMA
            ema_fast = prices.ewm(span=fast).mean()
            ema_slow = prices.ewm(span=slow).mean()
            
            # 计算DIF和DEA
            dif = ema_fast - ema_slow
            dea = dif.ewm(span=signal).mean()
            macd = (dif - dea) * 2
            
            return {
                'macd_dif': round(float(dif.iloc[-1]), 4) if not pd.isna(dif.iloc[-1]) else 0,
                'macd_dea': round(float(dea.iloc[-1]), 4) if not pd.isna(dea.iloc[-1]) else 0,
                'macd': round(float(macd.iloc[-1]), 4) if not pd.isna(macd.iloc[-1]) else 0
            }
        except Exception as e:
            logger.error(f"计算MACD失败: {e}")
            return {}
    
    @staticmethod
    def _calculate_kdj(data, n=9):
        """计算KDJ指标"""
        try:
            import pandas as pd
            
            df = pd.DataFrame(data)
            
            # 计算RSV
            low_min = df['low'].rolling(window=n).min()
            high_max = df['high'].rolling(window=n).max()
            rsv = (df['close'] - low_min) / (high_max - low_min) * 100
            
            # 计算K、D、J
            k = rsv.ewm(alpha=1/3).mean()
            d = k.ewm(alpha=1/3).mean()
            j = 3 * k - 2 * d
            
            return {
                'kdj_k': round(float(k.iloc[-1]), 2) if not pd.isna(k.iloc[-1]) else 0,
                'kdj_d': round(float(d.iloc[-1]), 2) if not pd.isna(d.iloc[-1]) else 0,
                'kdj_j': round(float(j.iloc[-1]), 2) if not pd.isna(j.iloc[-1]) else 0
            }
        except Exception as e:
            logger.error(f"计算KDJ失败: {e}")
            return {}
    
    @staticmethod
    def _calculate_rsi(prices, periods=[6, 12, 24]):
        """计算RSI指标"""
        try:
            import pandas as pd
            
            prices = pd.Series(prices)
            delta = prices.diff()
            
            result = {}
            for period in periods:
                if len(prices) >= period:
                    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    
                    result[f'rsi_{period}'] = round(float(rsi.iloc[-1]), 2) if not pd.isna(rsi.iloc[-1]) else 0
            
            return result
        except Exception as e:
            logger.error(f"计算RSI失败: {e}")
            return {}
    
    @staticmethod
    def _calculate_bollinger_bands(prices, window=20, num_std=2):
        """计算布林带指标"""
        try:
            import pandas as pd
            
            prices = pd.Series(prices)
            
            if len(prices) >= window:
                rolling_mean = prices.rolling(window=window).mean()
                rolling_std = prices.rolling(window=window).std()
                
                upper_band = rolling_mean + (rolling_std * num_std)
                lower_band = rolling_mean - (rolling_std * num_std)
                
                return {
                    'boll_upper': round(float(upper_band.iloc[-1]), 2) if not pd.isna(upper_band.iloc[-1]) else 0,
                    'boll_mid': round(float(rolling_mean.iloc[-1]), 2) if not pd.isna(rolling_mean.iloc[-1]) else 0,
                    'boll_lower': round(float(lower_band.iloc[-1]), 2) if not pd.isna(lower_band.iloc[-1]) else 0
                }
            
            return {}
        except Exception as e:
            logger.error(f"计算布林带失败: {e}")
            return {} 