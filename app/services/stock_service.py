from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.utils.cache import cached
from app.services.data_reader import ParquetDataReader
from loguru import logger
import pandas as pd
import numpy as np

_data_reader = ParquetDataReader()

class StockService:
    """股票数据服务类"""
    
    @staticmethod
    @cached(expire=1800, key_prefix='stock_basic')
    def get_stock_list(industry=None, area=None, search=None, page=1, page_size=20):
        """获取股票列表"""
        try:
            df = _data_reader.get_stock_basic_list(industry=industry, area=area, search=search)
            total = len(df)
            offset = (page - 1) * page_size
            page_df = df.iloc[offset:offset + page_size]

            stocks = page_df.where(page_df.notna(), None).to_dict(orient="records")
            # list_date 转 string
            for s in stocks:
                if hasattr(s.get("list_date"), "strftime"):
                    s["list_date"] = s["list_date"].strftime("%Y-%m-%d")
                elif s.get("list_date") is not None:
                    s["list_date"] = str(s["list_date"])

            return {
                'stocks': stocks,
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
            df = _data_reader.get_stock_basic(ts_code=ts_code)
            if df.empty:
                return None
            row = df.iloc[0].to_dict()
            row = {k: (v if not pd.isna(v) else None) for k, v in row.items()}
            if hasattr(row.get("list_date"), "strftime"):
                row["list_date"] = row["list_date"].strftime("%Y-%m-%d")
            elif row.get("list_date") is not None:
                row["list_date"] = str(row["list_date"])
            return row
        except Exception as e:
            logger.error(f"获取股票信息失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=300, key_prefix='daily_history')
    def get_daily_history(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 60):
        """获取股票日线历史数据"""
        try:
            df = _data_reader.get_daily(
                ts_codes=[ts_code], start_date=start_date, end_date=end_date
            )
            if df.empty:
                return []

            # 按日期倒序排列，取最新的 limit 条
            df = df.sort_values("trade_date", ascending=False).head(limit)
            # 转为 dict list（与原 ORM to_dict 兼容）
            df = df.copy()
            df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
            # NaN → None，避免 JSON 序列化出 NaN（非法 JSON）
            return df.where(df.notna(), None).to_dict(orient="records")
        except Exception as e:
            logger.error(f"获取日线历史数据失败: {ts_code}, 错误: {e}")
            return []
    
    @staticmethod
    @cached(expire=300, key_prefix='daily_basic')
    def get_daily_basic(ts_code: str, trade_date: str = None):
        """获取股票日线基本数据"""
        try:
            df = _data_reader.get_daily_basic(
                ts_codes=[ts_code], start_date=trade_date, end_date=trade_date
            )
            if df.empty:
                # 如果指定日期没数据，取最新一条
                df = _data_reader.get_daily_basic(ts_codes=[ts_code])
                if df.empty:
                    return None
                df = df.sort_values("trade_date", ascending=False).head(1)

            row = df.iloc[0].to_dict()
            # trade_date 转为字符串
            if hasattr(row.get("trade_date"), "strftime"):
                row["trade_date"] = row["trade_date"].strftime("%Y-%m-%d")
            return row
        except Exception as e:
            logger.error(f"获取日线基本数据失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=300, key_prefix='stock_factor')
    def get_stock_factors(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 60):
        """获取股票技术因子数据"""
        try:
            df = _data_reader.get_stk_factor(
                ts_codes=[ts_code], start_date=start_date, end_date=end_date
            )
            if df.empty or len(df) < limit:
                logger.info(f"stk_factor parquet 数据不足({len(df)}条)，基于历史数据计算技术指标")
                history_data = StockService.get_daily_history(ts_code, start_date, end_date, limit)
                if history_data:
                    return StockService._calculate_technical_indicators(history_data)

            df = df.sort_values("trade_date", ascending=False).head(limit)
            df = df.copy()
            df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
            return df.where(df.notna(), None).to_dict(orient="records")
        except Exception as e:
            logger.error(f"获取技术因子数据失败: {ts_code}, 错误: {e}")
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
            row = _data_reader.get_ma_data(ts_code)
            if row is None:
                return None
            d = row.to_dict()
            # Convert any numpy types and NaN
            for k, v in d.items():
                if pd.isna(v):
                    d[k] = None
                elif hasattr(v, 'item'):
                    d[k] = v.item()
            return d
        except Exception as e:
            logger.error(f"获取均线数据失败: {ts_code}, 错误: {e}")
            return None
    
    @staticmethod
    @cached(expire=300, key_prefix='moneyflow')
    def get_moneyflow(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 30):
        """获取股票资金流向数据"""
        try:
            df = _data_reader.get_moneyflow(
                ts_codes=[ts_code], start_date=start_date, end_date=end_date
            )
            if df.empty:
                return []

            df = df.sort_values("trade_date", ascending=False).head(limit)
            df = df.copy()
            df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
            records = df.where(df.notna(), None).to_dict(orient="records")
            return list(reversed(records))
        except Exception as e:
            logger.error(f"获取资金流向数据失败: {ts_code}, 错误: {e}")
            return []
    
    @staticmethod
    @cached(expire=300, key_prefix='cyq_perf')
    def get_cyq_perf(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 30):
        """获取股票筹码分布数据"""
        try:
            df = _data_reader.get_cyq_perf(
                ts_codes=[ts_code], start_date=start_date, end_date=end_date
            )
            if df.empty:
                return []

            df = df.sort_values("trade_date", ascending=False).head(limit)
            df = df.copy()
            df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
            records = df.where(df.notna(), None).to_dict(orient="records")
            return list(reversed(records))
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
            return _data_reader.get_industry_list()
        except Exception as e:
            logger.error(f"获取行业列表失败: {e}")
            return []

    @staticmethod
    @cached(expire=1800, key_prefix='area_list')
    def get_area_list():
        """获取地域列表"""
        try:
            return _data_reader.get_area_list()
        except Exception as e:
            logger.error(f"获取地域列表失败: {e}")
            return []
    
    @staticmethod
    def screen_stocks(criteria: Dict):
        """基于 Parquet 大宽表的增强筛选（原 MySQL JOIN 已迁移）"""
        try:
            # 1. 确定查询日期
            trade_date = criteria.get('trade_date')
            if not trade_date:
                trade_date = _data_reader.get_stock_business_latest_date()
            if not trade_date:
                return {'stocks': [], 'total': 0, 'criteria': criteria, 'error': '无可用的 trade_date'}

            # 2. 按日期加载 stock_business（~5000 行 / 天）
            biz = _data_reader.get_stock_business(trade_date=trade_date)
            if biz.empty:
                return {'stocks': [], 'total': 0, 'criteria': criteria}

            # 3. 加载 stock_basic 用于行业/地域/名称
            basic = _data_reader.get_stock_basic()

            # 在 basic 中选取需要的列
            basic_cols = ['ts_code', 'industry', 'area', 'symbol', 'name', 'list_date']
            basic_sub = basic[[c for c in basic_cols if c in basic.columns]].copy()

            # merge
            df = biz.merge(basic_sub, on='ts_code', how='left')

            # 4. 应用筛选条件
            # 行业 / 地域 / 市场
            if criteria.get('industry') and 'industry' in df.columns:
                df = df[df['industry'] == criteria['industry']]
            if criteria.get('area') and 'area' in df.columns:
                df = df[df['area'] == criteria['area']]
            if criteria.get('market') and 'ts_code' in df.columns:
                m = criteria['market']
                if m == 'SZ':
                    df = df[df['ts_code'].str.endswith('.SZ')]
                elif m == 'SH':
                    df = df[df['ts_code'].str.endswith('.SH')]

            # 范围过滤辅助
            def _range_filter(data, col, lo=None, hi=None):
                if col not in data.columns:
                    return data
                if lo is not None:
                    data = data[pd.to_numeric(data[col], errors='coerce') >= float(lo)]
                if hi is not None:
                    data = data[pd.to_numeric(data[col], errors='coerce') <= float(hi)]
                return data

            # 估值
            df = _range_filter(df, 'pe', criteria.get('pe_min'), criteria.get('pe_max'))
            df = _range_filter(df, 'pb', criteria.get('pb_min'), criteria.get('pb_max'))
            df = _range_filter(df, 'ps', criteria.get('ps_min'), criteria.get('ps_max'))
            df = _range_filter(df, 'dv_ratio', criteria.get('dv_min'), criteria.get('dv_max'))

            # 市值 / 交易
            df = _range_filter(df, 'total_mv', criteria.get('mv_min'), criteria.get('mv_max'))
            df = _range_filter(df, 'circ_mv', criteria.get('circ_mv_min'), criteria.get('circ_mv_max'))
            df = _range_filter(df, 'turnover_rate', criteria.get('turnover_min'), criteria.get('turnover_max'))
            df = _range_filter(df, 'volume_ratio', criteria.get('volume_ratio_min'), criteria.get('volume_ratio_max'))

            # 技术指标
            df = _range_filter(df, 'factor_rsi_6', criteria.get('rsi6_min'), criteria.get('rsi6_max'))
            df = _range_filter(df, 'factor_kdj_k', criteria.get('kdj_k_min'), criteria.get('kdj_k_max'))
            df = _range_filter(df, 'factor_macd', criteria.get('macd_min'), criteria.get('macd_max'))
            df = _range_filter(df, 'factor_cci', criteria.get('cci_min'), criteria.get('cci_max'))

            # 资金流向
            df = _range_filter(df, 'moneyflow_net_amount', criteria.get('net_amount_min'), criteria.get('net_amount_max'))
            df = _range_filter(df, 'moneyflow_buy_lg_amount_rate', criteria.get('lg_buy_rate_min'), criteria.get('lg_buy_rate_max'))
            df = _range_filter(df, 'moneyflow_net_d5_amount', criteria.get('net_d5_amount_min'), criteria.get('net_d5_amount_max'))

            # 5. 动态条件
            op_map = {'>': '__gt__', '>=': '__ge__', '<': '__lt__', '<=': '__le__',
                      '=': '__eq__', '!=': '__ne__'}
            for cond in criteria.get('dynamic_conditions', []):
                field_a = cond.get('field_a')
                operator = cond.get('operator')
                field_b = cond.get('field_b')
                value = cond.get('value')
                if not field_a or not operator or field_a not in df.columns:
                    continue
                col_a = pd.to_numeric(df[field_a], errors='coerce')
                if field_b and field_b in df.columns:
                    col_b = pd.to_numeric(df[field_b], errors='coerce')
                    method = op_map.get(operator)
                    if method:
                        df = df[getattr(col_a, method)(col_b)]
                elif value is not None:
                    try:
                        val = float(value)
                        method = op_map.get(operator)
                        if method:
                            df = df[getattr(col_a, method)(val)]
                    except ValueError:
                        logger.warning(f"动态条件值转换失败: {value}")

            # 6. 转换为字典列表
            # 确保 list_date 为字符串
            if 'list_date' in df.columns:
                df['list_date'] = df['list_date'].apply(
                    lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else (str(x) if pd.notna(x) else None)
                )
            # trade_date 统一为字符串
            if 'trade_date' in df.columns:
                df['trade_date'] = df['trade_date'].apply(
                    lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else (str(x) if pd.notna(x) else None)
                )

            stocks = df.where(df.notna(), None).to_dict(orient='records')

            # 限制返回数量
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
