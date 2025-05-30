"""
实时数据管理服务
负责分钟级数据的接入、聚合、质量监控等功能
集成Baostock数据源支持
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from app.models.stock_minute_data import StockMinuteData
from app.extensions import db
from app.services.minute_data_sync_service import MinuteDataSyncService

# 可选导入tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    ts = None

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealtimeDataManager:
    """实时数据管理器"""
    
    def __init__(self, tushare_token: Optional[str] = None):
        """
        初始化实时数据管理器
        
        Args:
            tushare_token: Tushare API token
        """
        self.tushare_token = tushare_token
        if tushare_token and TUSHARE_AVAILABLE:
            ts.set_token(tushare_token)
            self.pro = ts.pro_api()
        else:
            self.pro = None
            if not TUSHARE_AVAILABLE:
                logger.warning("Tushare未安装，将使用Baostock数据源")
            else:
                logger.warning("未设置Tushare token，将使用Baostock数据源")
        
        # 初始化分钟数据同步服务
        self.minute_sync_service = MinuteDataSyncService()
    
    def sync_minute_data(self, ts_code: str, start_date: str = None, end_date: str = None, 
                        period_type: str = '1min', use_baostock: bool = True) -> Dict:
        """
        同步分钟级数据
        
        Args:
            ts_code: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period_type: 周期类型
            use_baostock: 是否使用Baostock数据源
            
        Returns:
            同步结果
        """
        try:
            # 设置默认日期范围
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            logger.info(f"开始同步 {ts_code} 从 {start_date} 到 {end_date} 的{period_type}数据")
            
            if use_baostock:
                # 使用Baostock数据源
                with self.minute_sync_service as sync_service:
                    result = sync_service.sync_single_stock_data(
                        ts_code, period_type, start_date, end_date
                    )
                return result
            else:
                # 使用原有的模拟数据或Tushare数据源
                return self._sync_minute_data_legacy(ts_code, start_date, end_date, period_type)
            
        except Exception as e:
            logger.error(f"同步数据失败: {str(e)}")
            return {
                'success': False,
                'message': f'同步失败: {str(e)}',
                'data_count': 0
            }
    
    def sync_multiple_stocks_data(self, stock_list: List[str], period_type: str = '1min',
                                 start_date: str = None, end_date: str = None,
                                 batch_size: int = 10, use_baostock: bool = True) -> Dict:
        """
        批量同步多个股票的分钟数据
        
        Args:
            stock_list: 股票代码列表
            period_type: 周期类型
            start_date: 开始日期
            end_date: 结束日期
            batch_size: 批处理大小
            use_baostock: 是否使用Baostock数据源
            
        Returns:
            同步结果字典
        """
        try:
            if use_baostock:
                # 使用Baostock数据源
                with self.minute_sync_service as sync_service:
                    result = sync_service.sync_multiple_stocks_data(
                        stock_list, period_type, start_date, end_date, batch_size
                    )
                return result
            else:
                # 使用原有方式逐个同步
                total_stocks = len(stock_list)
                success_stocks = 0
                failed_stocks = 0
                total_data_count = 0
                
                for ts_code in stock_list:
                    result = self.sync_minute_data(ts_code, start_date, end_date, period_type, False)
                    if result['success']:
                        success_stocks += 1
                        total_data_count += result.get('data_count', 0)
                    else:
                        failed_stocks += 1
                
                return {
                    'success': True,
                    'message': '批量同步完成',
                    'total_stocks': total_stocks,
                    'success_stocks': success_stocks,
                    'failed_stocks': failed_stocks,
                    'total_data_count': total_data_count,
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
    
    def sync_all_periods_for_stock(self, ts_code: str, start_date: str = None, 
                                  end_date: str = None, use_baostock: bool = True) -> Dict:
        """
        同步单个股票的所有周期数据
        
        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            use_baostock: 是否使用Baostock数据源
            
        Returns:
            同步结果字典
        """
        try:
            if use_baostock:
                with self.minute_sync_service as sync_service:
                    result = sync_service.sync_all_periods_for_stock(ts_code, start_date, end_date)
                return result
            else:
                # 使用原有方式
                results = {}
                period_types = ['1min', '5min', '15min', '30min', '60min']
                
                for period_type in period_types:
                    result = self.sync_minute_data(ts_code, start_date, end_date, period_type, False)
                    results[period_type] = result
                
                return results
                
        except Exception as e:
            logger.error(f"同步所有周期数据异常: {e}")
            return {
                'error': f'同步异常: {str(e)}'
            }
    
    def get_stock_list_from_db(self) -> List[str]:
        """
        从数据库获取股票列表
        """
        return self.minute_sync_service.get_stock_list_from_db()
    
    def _sync_minute_data_legacy(self, ts_code: str, start_date: str, end_date: str, period_type: str) -> Dict:
        """
        原有的同步方式（保持兼容性）
        """
        try:
            # 转换日期格式
            start_date_legacy = datetime.strptime(start_date, '%Y-%m-%d').strftime('%Y%m%d')
            end_date_legacy = datetime.strptime(end_date, '%Y-%m-%d').strftime('%Y%m%d')
            
            logger.info(f"使用原有方式同步 {ts_code} 从 {start_date_legacy} 到 {end_date_legacy} 的{period_type}数据")
            
            # 获取1分钟数据（这里使用模拟数据，实际应该调用真实API）
            minute_data = self._fetch_minute_data_from_source(ts_code, start_date_legacy, end_date_legacy)
            
            if minute_data.empty:
                return {
                    'success': False,
                    'message': '未获取到数据',
                    'data_count': 0
                }
            
            # 转换数据格式
            data_list = self._convert_to_model_format(minute_data, ts_code, period_type)
            
            # 批量插入数据
            StockMinuteData.bulk_insert(data_list)
            
            # 如果是1分钟数据，生成其他周期数据
            if period_type == '1min':
                self._generate_aggregated_data(ts_code, start_date_legacy, end_date_legacy)
            
            logger.info(f"成功同步 {len(data_list)} 条 {ts_code} 的{period_type}数据")
            
            return {
                'success': True,
                'message': f'成功同步 {len(data_list)} 条数据',
                'data_count': len(data_list),
                'ts_code': ts_code,
                'start_date': start_date,
                'end_date': end_date,
                'period_type': period_type
            }
            
        except Exception as e:
            logger.error(f"同步数据失败: {str(e)}")
            return {
                'success': False,
                'message': f'同步失败: {str(e)}',
                'data_count': 0
            }
    
    def _fetch_minute_data_from_source(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从数据源获取分钟数据（模拟实现）
        实际使用时应该替换为真实的数据源API调用
        """
        try:
            # 这里使用模拟数据，实际应该调用真实API
            # 例如: self.pro.stk_mins(ts_code=ts_code, start_date=start_date, end_date=end_date)
            
            # 生成模拟的分钟数据
            start_dt = datetime.strptime(start_date, '%Y%m%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d')
            
            # 生成交易时间范围内的分钟数据
            data_list = []
            current_dt = start_dt
            base_price = 10.0  # 基础价格
            
            while current_dt <= end_dt:
                # 只在交易时间生成数据 (9:30-11:30, 13:00-15:00)
                if current_dt.weekday() < 5:  # 工作日
                    # 上午时段
                    for hour in range(9, 12):
                        start_minute = 30 if hour == 9 else 0
                        end_minute = 30 if hour == 11 else 60
                        
                        for minute in range(start_minute, end_minute):
                            dt = current_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            
                            # 生成模拟价格数据
                            price_change = np.random.normal(0, 0.01)  # 随机价格变动
                            open_price = base_price * (1 + price_change)
                            high_price = open_price * (1 + abs(np.random.normal(0, 0.005)))
                            low_price = open_price * (1 - abs(np.random.normal(0, 0.005)))
                            close_price = open_price + np.random.normal(0, 0.005)
                            volume = np.random.randint(1000, 10000)
                            amount = volume * close_price
                            
                            data_list.append({
                                'trade_date': dt.strftime('%Y%m%d'),
                                'trade_time': dt.strftime('%H%M'),
                                'open': round(open_price, 2),
                                'high': round(high_price, 2),
                                'low': round(low_price, 2),
                                'close': round(close_price, 2),
                                'vol': volume,
                                'amount': round(amount, 2)
                            })
                            
                            base_price = close_price  # 更新基础价格
                    
                    # 下午时段
                    for hour in range(13, 15):
                        for minute in range(0, 60):
                            dt = current_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            
                            # 生成模拟价格数据
                            price_change = np.random.normal(0, 0.01)
                            open_price = base_price * (1 + price_change)
                            high_price = open_price * (1 + abs(np.random.normal(0, 0.005)))
                            low_price = open_price * (1 - abs(np.random.normal(0, 0.005)))
                            close_price = open_price + np.random.normal(0, 0.005)
                            volume = np.random.randint(1000, 10000)
                            amount = volume * close_price
                            
                            data_list.append({
                                'trade_date': dt.strftime('%Y%m%d'),
                                'trade_time': dt.strftime('%H%M'),
                                'open': round(open_price, 2),
                                'high': round(high_price, 2),
                                'low': round(low_price, 2),
                                'close': round(close_price, 2),
                                'vol': volume,
                                'amount': round(amount, 2)
                            })
                            
                            base_price = close_price
                
                current_dt += timedelta(days=1)
            
            return pd.DataFrame(data_list)
            
        except Exception as e:
            logger.error(f"获取数据源数据失败: {str(e)}")
            return pd.DataFrame()
    
    def _convert_to_model_format(self, df: pd.DataFrame, ts_code: str, period_type: str) -> List[Dict]:
        """
        将数据源格式转换为模型格式
        """
        data_list = []
        
        for _, row in df.iterrows():
            # 构造完整的datetime
            trade_date = str(row['trade_date'])
            trade_time = str(row['trade_time']).zfill(4)  # 确保4位数
            
            dt_str = f"{trade_date} {trade_time[:2]}:{trade_time[2:]}:00"
            dt = datetime.strptime(dt_str, '%Y%m%d %H:%M:%S')
            
            # 计算涨跌幅等指标
            pre_close = row.get('pre_close', row['open'])
            change = row['close'] - pre_close
            pct_chg = (change / pre_close * 100) if pre_close > 0 else 0
            
            data_list.append({
                'ts_code': ts_code,
                'datetime': dt,
                'period_type': period_type,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['vol'],
                'amount': row['amount'],
                'pre_close': pre_close,
                'change': change,
                'pct_chg': pct_chg
            })
        
        return data_list
    
    def aggregate_data(self, ts_code: str, source_period: str = '1min', target_period: str = '5min', 
                      start_date: str = None, end_date: str = None) -> Dict:
        """
        数据聚合：将小周期数据聚合为大周期数据
        
        Args:
            ts_code: 股票代码
            source_period: 源周期
            target_period: 目标周期
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            聚合结果
        """
        try:
            # 设置默认日期范围
            if not end_date:
                end_date = datetime.now()
            else:
                end_date = datetime.strptime(end_date, '%Y%m%d')
            
            if not start_date:
                start_date = end_date - timedelta(days=7)
            else:
                start_date = datetime.strptime(start_date, '%Y%m%d')
            
            # 获取源数据
            source_data = StockMinuteData.get_data_by_time_range(
                ts_code, start_date, end_date, source_period
            )
            
            if not source_data:
                return {
                    'success': False,
                    'message': f'没有找到 {ts_code} 的 {source_period} 数据',
                    'data_count': 0
                }
            
            # 转换为DataFrame
            df = pd.DataFrame([data.to_dict() for data in source_data])
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            
            # 确定聚合频率
            freq_map = {
                '5min': '5T',
                '15min': '15T',
                '30min': '30T',
                '60min': '60T'
            }
            
            if target_period not in freq_map:
                return {
                    'success': False,
                    'message': f'不支持的目标周期: {target_period}',
                    'data_count': 0
                }
            
            freq = freq_map[target_period]
            
            # 执行聚合
            agg_data = df.resample(freq).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
                'amount': 'sum'
            }).dropna()
            
            # 计算技术指标
            agg_data['pre_close'] = agg_data['close'].shift(1)
            agg_data['change'] = agg_data['close'] - agg_data['pre_close']
            agg_data['pct_chg'] = (agg_data['change'] / agg_data['pre_close'] * 100).fillna(0)
            
            # 转换为模型格式
            aggregated_list = []
            for dt, row in agg_data.iterrows():
                if pd.notna(row['open']):  # 确保数据有效
                    aggregated_list.append({
                        'ts_code': ts_code,
                        'datetime': dt.to_pydatetime(),
                        'period_type': target_period,
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'volume': int(row['volume']),
                        'amount': row['amount'],
                        'pre_close': row['pre_close'] if pd.notna(row['pre_close']) else row['open'],
                        'change': row['change'] if pd.notna(row['change']) else 0,
                        'pct_chg': row['pct_chg'] if pd.notna(row['pct_chg']) else 0
                    })
            
            # 批量插入聚合数据
            if aggregated_list:
                StockMinuteData.bulk_insert(aggregated_list)
            
            logger.info(f"成功聚合 {len(aggregated_list)} 条 {target_period} 数据")
            
            return {
                'success': True,
                'message': f'成功聚合 {len(aggregated_list)} 条 {target_period} 数据',
                'data_count': len(aggregated_list),
                'source_period': source_period,
                'target_period': target_period
            }
            
        except Exception as e:
            logger.error(f"数据聚合失败: {str(e)}")
            return {
                'success': False,
                'message': f'聚合失败: {str(e)}',
                'data_count': 0
            }
    
    def _generate_aggregated_data(self, ts_code: str, start_date: str, end_date: str):
        """生成所有周期的聚合数据"""
        periods = ['5min', '15min', '30min', '60min']
        
        for period in periods:
            try:
                result = self.aggregate_data(ts_code, '1min', period, start_date, end_date)
                if result['success']:
                    logger.info(f"生成 {period} 聚合数据成功: {result['data_count']} 条")
                else:
                    logger.warning(f"生成 {period} 聚合数据失败: {result['message']}")
            except Exception as e:
                logger.error(f"生成 {period} 聚合数据异常: {str(e)}")
    
    def check_data_quality(self, ts_code: str, period_type: str = '1min', hours: int = 24) -> Dict:
        """
        检查数据质量
        
        Args:
            ts_code: 股票代码
            period_type: 周期类型
            hours: 检查的小时数
            
        Returns:
            质量检查结果
        """
        try:
            return StockMinuteData.check_data_quality(ts_code, period_type, hours)
        except Exception as e:
            logger.error(f"数据质量检查失败: {str(e)}")
            return {
                'status': 'error',
                'message': f'检查失败: {str(e)}',
                'data_count': 0,
                'missing_count': 0,
                'completeness': 0.0
            }
    
    def get_realtime_price(self, ts_code: str) -> Dict:
        """
        获取实时价格信息
        
        Args:
            ts_code: 股票代码
            
        Returns:
            实时价格信息
        """
        try:
            latest_data = StockMinuteData.query.filter_by(
                ts_code=ts_code,
                period_type='1min'
            ).order_by(StockMinuteData.datetime.desc()).first()
            
            if not latest_data:
                return {
                    'success': False,
                    'message': f'未找到 {ts_code} 的实时数据',
                    'data': None
                }
            
            return {
                'success': True,
                'message': '获取成功',
                'data': {
                    'ts_code': latest_data.ts_code,
                    'current_price': latest_data.close,
                    'change': latest_data.change,
                    'pct_chg': latest_data.pct_chg,
                    'volume': latest_data.volume,
                    'amount': latest_data.amount,
                    'update_time': latest_data.datetime.isoformat(),
                    'open': latest_data.open,
                    'high': latest_data.high,
                    'low': latest_data.low
                }
            }
            
        except Exception as e:
            logger.error(f"获取实时价格失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}',
                'data': None
            }
    
    def get_market_overview(self) -> Dict:
        """
        获取市场概览信息
        
        Returns:
            市场概览数据
        """
        try:
            # 获取所有股票的最新数据
            latest_time = db.session.query(
                db.func.max(StockMinuteData.datetime)
            ).filter_by(period_type='1min').scalar()
            
            if not latest_time:
                return {
                    'success': False,
                    'message': '没有找到市场数据',
                    'data': None
                }
            
            # 获取最新时间的所有股票数据
            latest_data = StockMinuteData.query.filter_by(
                period_type='1min'
            ).filter(
                StockMinuteData.datetime >= latest_time - timedelta(minutes=5)
            ).all()
            
            if not latest_data:
                return {
                    'success': False,
                    'message': '没有找到最新市场数据',
                    'data': None
                }
            
            # 统计市场数据
            total_stocks = len(latest_data)
            rising_stocks = len([d for d in latest_data if d.pct_chg > 0])
            falling_stocks = len([d for d in latest_data if d.pct_chg < 0])
            flat_stocks = total_stocks - rising_stocks - falling_stocks
            
            total_volume = sum([d.volume for d in latest_data])
            total_amount = sum([d.amount for d in latest_data])
            
            avg_pct_chg = np.mean([d.pct_chg for d in latest_data if d.pct_chg is not None])
            
            return {
                'success': True,
                'message': '获取成功',
                'data': {
                    'update_time': latest_time.isoformat(),
                    'total_stocks': total_stocks,
                    'rising_stocks': rising_stocks,
                    'falling_stocks': falling_stocks,
                    'flat_stocks': flat_stocks,
                    'rising_ratio': round(rising_stocks / total_stocks * 100, 2) if total_stocks > 0 else 0,
                    'total_volume': total_volume,
                    'total_amount': round(total_amount, 2),
                    'avg_pct_chg': round(avg_pct_chg, 2) if not np.isnan(avg_pct_chg) else 0
                }
            }
            
        except Exception as e:
            logger.error(f"获取市场概览失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}',
                'data': None
            } 