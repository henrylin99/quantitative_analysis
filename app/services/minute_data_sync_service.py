"""
分钟级数据同步服务
整合1、5、15、30、60分钟K线数据获取功能
适配 Parquet 持久化系统
"""

import baostock as bs
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional
from app.services.minute_parquet_store import MinuteParquetStore
import time

logger = logging.getLogger(__name__)

class MinuteDataSyncService:
    """分钟级数据同步服务"""
    
    # 支持的周期类型
    PERIOD_TYPES = {
        '1min': '1',
        '5min': '5', 
        '15min': '15',
        '30min': '30',
        '60min': '60'
    }
    
    def __init__(self):
        self.bs_logged_in = False
        self.parquet_store = MinuteParquetStore()
        
    def __enter__(self):
        """上下文管理器入口"""
        self.login_baostock()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.logout_baostock()
        
    def login_baostock(self):
        """登录Baostock"""
        try:
            lg = bs.login()
            if lg.error_code == '0':
                self.bs_logged_in = True
                logger.info("Baostock登录成功")
            else:
                logger.error(f"Baostock登录失败: {lg.error_msg}")
                raise Exception(f"Baostock登录失败: {lg.error_msg}")
        except Exception as e:
            logger.error(f"Baostock登录异常: {e}")
            raise e
            
    def logout_baostock(self):
        """登出Baostock"""
        if self.bs_logged_in:
            bs.logout()
            self.bs_logged_in = False
            logger.info("Baostock登出成功")
    
    def convert_ts_code_to_bs_code(self, ts_code: str) -> str:
        """
        转换股票代码格式
        支持以下输入，并统一输出为 Baostock 格式:
        000001.SZ -> sz.000001
        600000.SH -> sh.600000
        sz.300502 -> sz.300502
        """
        code = str(ts_code).strip()
        lower_code = code.lower()

        if lower_code.startswith(('sz.', 'sh.')):
            return lower_code
        if lower_code.endswith('.sz'):
            return 'sz.' + lower_code.split('.')[0]
        if lower_code.endswith('.sh'):
            return 'sh.' + lower_code.split('.')[0]
        return lower_code
    
    def get_stock_minute_data_bs(self, stock_code: str, start_date: str, 
                                end_date: str, period_type: str = '1min') -> Optional[pd.DataFrame]:
        """
        使用Baostock获取股票分钟线数据
        
        Args:
            stock_code: 股票代码，如 'sh.600519'、'sz.300502' 或 '600519.SH'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            period_type: 周期类型，如 '1min', '5min', '15min', '30min', '60min'
            
        Returns:
            DataFrame包含分钟线数据
        """
        try:
            # 转换股票代码格式
            bs_code = self.convert_ts_code_to_bs_code(stock_code)
            
            # 获取Baostock频率参数
            frequency = self.PERIOD_TYPES.get(period_type, '5')  # 默认使用5分钟
            
            # 注意：Baostock可能不支持1分钟数据，如果是1分钟则改为5分钟
            if period_type == '1min':
                logger.warning(f"Baostock不支持1分钟数据，改为使用5分钟数据: {bs_code}")
                frequency = '5'
                actual_period = '5min'
            else:
                actual_period = period_type
            
            # 查询历史K线数据
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,time,code,open,high,low,close,volume,amount",
                start_date=start_date, 
                end_date=end_date,
                frequency=frequency, 
                adjustflag="3"  # 后复权
            )
            
            if rs.error_code != '0':
                logger.error(f"获取{bs_code}数据失败: {rs.error_msg}")
                return None
            
            # 收集数据
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                logger.warning(f"未获取到{bs_code}的{period_type}数据")
                return None
                
            # 创建DataFrame
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # 数据预处理
            df = self._preprocess_dataframe(df, actual_period)
            
            logger.info(f"成功获取{bs_code}的{actual_period}数据，共{len(df)}条记录")
            return df
            
        except Exception as e:
            logger.error(f"获取{stock_code}的{period_type}数据异常: {e}")
            return None
    
    def _preprocess_dataframe(self, df: pd.DataFrame, period_type: str) -> pd.DataFrame:
        """
        预处理DataFrame数据
        """
        if df.empty:
            return df
            
        try:
            # 处理时间字段
            df['datetime'] = df['time'].apply(self._parse_time_string)
            
            # 转换数据类型
            numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'amount']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 添加周期类型
            df['period_type'] = period_type
            
            # 分钟线链路统一存储 Baostock 代码格式
            df['ts_code'] = df['code'].apply(self.convert_ts_code_to_bs_code)
            
            # 计算涨跌幅等字段
            df = self._calculate_technical_fields(df)
            
            # 删除不需要的列
            df = df.drop(['date', 'time', 'code'], axis=1, errors='ignore')
            
            # 去除空值行
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            
            return df
            
        except Exception as e:
            logger.error(f"预处理DataFrame异常: {e}")
            return df
    
    def _parse_time_string(self, time_str: str) -> datetime:
        """
        解析时间字符串
        格式: YYYYMMDDHHMMSS000 -> datetime
        """
        try:
            # 取前14位：YYYYMMDDHHMMSS
            time_str = str(time_str)[:14]
            
            # 解析各部分
            year = time_str[:4]
            month = time_str[4:6]
            day = time_str[6:8]
            hour = time_str[8:10]
            minute = time_str[10:12]
            second = time_str[12:14]
            
            # 构建datetime对象
            return datetime(
                int(year), int(month), int(day),
                int(hour), int(minute), int(second)
            )
        except Exception as e:
            logger.error(f"解析时间字符串失败: {time_str}, 错误: {e}")
            return datetime.now()
    
    def _calculate_technical_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标字段
        """
        try:
            # 按时间排序
            df = df.sort_values('datetime')
            
            # 计算前收盘价
            df['pre_close'] = df['close'].shift(1)
            
            # 计算涨跌额
            df['change'] = df['close'] - df['pre_close']
            
            # 计算涨跌幅(%)
            df['pct_chg'] = (df['change'] / df['pre_close'] * 100).round(4)
            
            # 处理第一行数据
            df.loc[df.index[0], 'pre_close'] = df.loc[df.index[0], 'close']
            df.loc[df.index[0], 'change'] = 0
            df.loc[df.index[0], 'pct_chg'] = 0
            
            return df
            
        except Exception as e:
            logger.error(f"计算技术指标字段异常: {e}")
            return df
    
    def sync_single_stock_data(self, ts_code: str, period_type: str = '1min',
                              start_date: str = None, end_date: str = None) -> Dict:
        """
        同步单个股票的分钟数据
        
        Args:
            ts_code: 股票代码
            period_type: 周期类型
            start_date: 开始日期，默认为7天前
            end_date: 结束日期，默认为今天
            
        Returns:
            同步结果字典
        """
        try:
            # 设置默认日期范围
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            logger.info(f"开始同步{ts_code}的{period_type}数据，时间范围: {start_date} 到 {end_date}")
            
            # 获取数据
            df = self.get_stock_minute_data_bs(ts_code, start_date, end_date, period_type)
            
            if df is None or df.empty:
                return {
                    'success': False,
                    'message': f'未获取到{ts_code}的{period_type}数据',
                    'data_count': 0
                }
            
            parquet_count = self.parquet_store.write_frame(df, period_type)
            success_count = parquet_count
            error_count = max(len(df) - parquet_count, 0)

            logger.info(f"同步{ts_code}的{period_type}数据完成，写入 Parquet: {parquet_count}, 失败: {error_count}")
            
            return {
                'success': True,
                'message': f'同步完成',
                'data_count': success_count,
                'parquet_count': parquet_count,
                'error_count': error_count,
                'period_type': period_type,
                'date_range': f'{start_date} 到 {end_date}'
            }
            
        except Exception as e:
            logger.error(f"同步{ts_code}的{period_type}数据异常: {e}")
            return {
                'success': False,
                'message': f'同步异常: {str(e)}',
                'data_count': 0
            }
    
    def sync_multiple_stocks_data(self, stock_list: List[str], period_type: str = '1min',
                                 start_date: str = None, end_date: str = None,
                                 batch_size: int = 10) -> Dict:
        """
        批量同步多个股票的分钟数据
        
        Args:
            stock_list: 股票代码列表
            period_type: 周期类型
            start_date: 开始日期
            end_date: 结束日期
            batch_size: 批处理大小
            
        Returns:
            同步结果字典
        """
        try:
            total_stocks = len(stock_list)
            success_stocks = 0
            failed_stocks = 0
            total_data_count = 0
            
            logger.info(f"开始批量同步{total_stocks}只股票的{period_type}数据")
            
            # 分批处理
            for i in range(0, total_stocks, batch_size):
                batch_stocks = stock_list[i:i + batch_size]
                
                for ts_code in batch_stocks:
                    try:
                        result = self.sync_single_stock_data(
                            ts_code, period_type, start_date, end_date
                        )
                        
                        if result['success']:
                            success_stocks += 1
                            total_data_count += result['data_count']
                        else:
                            failed_stocks += 1
                            
                        # 避免请求过于频繁
                        time.sleep(0.1)
                        
                    except Exception as e:
                        logger.error(f"同步{ts_code}异常: {e}")
                        failed_stocks += 1
                        continue
                
                # 批次间休息
                if i + batch_size < total_stocks:
                    time.sleep(1)
                    logger.info(f"已处理 {min(i + batch_size, total_stocks)}/{total_stocks} 只股票")
            
            logger.info(f"批量同步完成，成功: {success_stocks}, 失败: {failed_stocks}, 总数据量: {total_data_count}")
            
            return {
                'success': True,
                'message': '批量同步完成',
                'total_stocks': total_stocks,
                'success_stocks': success_stocks,
                'failed_stocks': failed_stocks,
                'total_data_count': total_data_count,
                'parquet_data_count': total_data_count,
                'period_type': period_type
            }
            
        except Exception as e:
            logger.error(f"批量同步异常: {e}")
            return {
                'success': False,
                'message': f'批量同步异常: {str(e)}',
                'total_stocks': len(stock_list),
                'success_stocks': 0,
                'failed_stocks': len(stock_list)
            }
    
    def get_stock_list_from_db(self) -> List[str]:
        """
        从 Parquet 股票基础资料获取股票列表
        """
        try:
            from app.services.data_reader import ParquetDataReader

            df = ParquetDataReader().get_stock_basic()
            if df.empty or "ts_code" not in df.columns:
                logger.warning("Parquet 股票基础资料为空")
                return []
            stock_list = df["ts_code"].dropna().astype(str).tolist()
            logger.info(f"从 Parquet 获取到{len(stock_list)}只股票")
            return stock_list
        except Exception as e:
            logger.error(f"获取股票列表异常: {e}")
            return []
    
    def sync_all_periods_for_stock(self, ts_code: str, start_date: str = None, 
                                  end_date: str = None) -> Dict:
        """
        同步单个股票的所有周期数据
        """
        results = {}
        
        for period_type in self.PERIOD_TYPES.keys():
            try:
                result = self.sync_single_stock_data(ts_code, period_type, start_date, end_date)
                results[period_type] = result
                
                # 周期间休息
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"同步{ts_code}的{period_type}数据异常: {e}")
                results[period_type] = {
                    'success': False,
                    'message': f'异常: {str(e)}',
                    'data_count': 0
                }
        
        return results 
