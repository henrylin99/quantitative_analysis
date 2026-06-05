"""
实时数据管理服务
负责分钟级数据的接入、聚合、质量监控等功能
集成多分钟数据源支持
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
import pandas as pd
from app.extensions import db
from app.services.minute_data_sync_service import MinuteDataSyncService
from app.services.tongdaxin_minute_sync_service import TongdaxinMinuteSyncService
from app.services.data_reader import ParquetDataReader
from app.services.minute_parquet_reader import MinuteParquetReader
from app.services.minute_parquet_store import MinuteParquetStore

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


LEGACY_REALTIME_SYNC_DISABLED_MESSAGE = 'legacy分钟数据同步已禁用，请使用真实数据源'


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
        self.tongdaxin_minute_sync_service = TongdaxinMinuteSyncService()
        self.data_reader = ParquetDataReader()
        self.minute_reader = self.data_reader.get_minute_reader()
        self.minute_store = MinuteParquetStore()
    
    def sync_minute_data(self, ts_code: str, start_date: str = None, end_date: str = None, 
                        period_type: str = '5min', use_baostock: bool = True, data_source: str = 'tongdaxin') -> Dict:
        """
        同步分钟级数据
        
        Args:
            ts_code: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period_type: 周期类型
            use_baostock: 是否使用Baostock数据源
            data_source: 分钟数据源名称
            
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
            
            source = self._resolve_minute_data_source(data_source, use_baostock)

            if source == 'tongdaxin':
                with self.tongdaxin_minute_sync_service as sync_service:
                    result = sync_service.sync_single_stock_data(
                        ts_code, period_type, start_date, end_date
                    )
                return result

            if source == 'baostock':
                # 使用Baostock数据源
                with self.minute_sync_service as sync_service:
                    result = sync_service.sync_single_stock_data(
                        ts_code, period_type, start_date, end_date
                    )
                return result

            return self._sync_minute_data_legacy(ts_code, start_date, end_date, period_type)
            
        except Exception as e:
            logger.error(f"同步数据失败: {str(e)}")
            return {
                'success': False,
                'message': f'同步失败: {str(e)}',
                'data_count': 0
            }
    
    def sync_multiple_stocks_data(self, stock_list: List[str], period_type: str = '5min',
                                 start_date: str = None, end_date: str = None,
                                 batch_size: int = 10, use_baostock: bool = True, data_source: str = 'tongdaxin') -> Dict:
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
            source = self._resolve_minute_data_source(data_source, use_baostock)

            if source not in {'baostock', 'tongdaxin'}:
                logger.warning("批量分钟数据legacy同步已禁用")
                return {
                    'success': False,
                    'message': LEGACY_REALTIME_SYNC_DISABLED_MESSAGE,
                    'total_stocks': len(stock_list),
                    'success_stocks': 0,
                    'failed_stocks': len(stock_list),
                    'total_data_count': 0,
                    'period_type': period_type
                }

            if source == 'tongdaxin':
                with self.tongdaxin_minute_sync_service as sync_service:
                    result = sync_service.sync_multiple_stocks_data(
                        stock_list, period_type, start_date, end_date, batch_size
                    )
                return result

            if source == 'baostock':
                # 使用Baostock数据源
                with self.minute_sync_service as sync_service:
                    result = sync_service.sync_multiple_stocks_data(
                        stock_list, period_type, start_date, end_date, batch_size
                    )
                return result
                
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
                                  end_date: str = None, use_baostock: bool = True, data_source: str = 'tongdaxin') -> Dict:
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
            source = self._resolve_minute_data_source(data_source, use_baostock)

            if source not in {'baostock', 'tongdaxin'}:
                logger.warning("全周期分钟数据legacy同步已禁用")
                return {
                    'success': False,
                    'message': LEGACY_REALTIME_SYNC_DISABLED_MESSAGE,
                    'ts_code': ts_code,
                    'period_types': ['1min', '5min', '15min', '30min', '60min']
                }

            if source == 'tongdaxin':
                with self.tongdaxin_minute_sync_service as sync_service:
                    result = sync_service.sync_all_periods_for_stock(ts_code, start_date, end_date)
                return result

            if source == 'baostock':
                with self.minute_sync_service as sync_service:
                    result = sync_service.sync_all_periods_for_stock(ts_code, start_date, end_date)
                return result
                
        except Exception as e:
            logger.error(f"同步所有周期数据异常: {e}")
            return {
                'error': f'同步异常: {str(e)}'
            }
    
    def get_stock_list_from_db(self) -> List[str]:
        """
        从 Parquet 股票基础资料获取股票列表
        """
        try:
            df = self.data_reader.get_stock_basic()
            if df.empty or "ts_code" not in df.columns:
                return []
            return df["ts_code"].dropna().astype(str).tolist()
        except Exception as e:
            logger.error(f"获取股票列表异常: {e}")
            return []
    
    def _sync_minute_data_legacy(self, ts_code: str, start_date: str, end_date: str, period_type: str) -> Dict:
        """
        原有的同步方式（保持兼容性）
        """
        logger.warning("legacy 分钟数据同步已禁用，避免写入模拟行情数据")
        return {
            'success': False,
            'message': LEGACY_REALTIME_SYNC_DISABLED_MESSAGE,
            'data_count': 0,
            'ts_code': ts_code,
            'start_date': start_date,
            'end_date': end_date,
            'period_type': period_type
        }

    def _resolve_minute_data_source(self, data_source: Optional[str], use_baostock: bool) -> str:
        if data_source:
            return str(data_source).strip().lower()
        return 'baostock' if use_baostock else 'tongdaxin'
    
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
                end_date = self._parse_aggregate_bound(end_date, is_end=True)
            
            if not start_date:
                start_date = end_date - timedelta(days=7)
            else:
                start_date = self._parse_aggregate_bound(start_date, is_end=False)
            
            source_data = self.get_minute_reader().get_data(
                ts_code=ts_code,
                period_type=source_period,
                start_time=start_date,
                end_time=end_date,
            )

            if source_data.empty:
                return {
                    'success': False,
                    'message': f'没有找到 {ts_code} 的 {source_period} 数据',
                    'data_count': 0
                }

            df = source_data.copy()
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            
            # 确定聚合频率
            freq_map = {
                '5min': '5min',
                '15min': '15min',
                '30min': '30min',
                '60min': '60min'
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
            
            parquet_written = 0
            if aggregated_list:
                aggregated_frame = pd.DataFrame(aggregated_list)
                parquet_written = self.minute_store.write_frame(aggregated_frame, target_period)

            logger.info(f"成功聚合 {len(aggregated_list)} 条 {target_period} 数据")
            
            return {
                'success': True,
                'message': f'成功聚合 {len(aggregated_list)} 条 {target_period} 数据',
                'data_count': len(aggregated_list),
                'parquet_count': parquet_written,
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

    def _parse_aggregate_bound(self, value: str, is_end: bool) -> datetime:
        """解析聚合日期边界，日期字符串按整日范围处理。"""
        text = str(value)
        if len(text) == 8 and text.isdigit():
            dt = datetime.strptime(text, "%Y%m%d")
            if is_end:
                return dt + timedelta(days=1) - timedelta(microseconds=1)
            return dt
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            dt = datetime.strptime(text, "%Y-%m-%d")
            if is_end:
                return dt + timedelta(days=1) - timedelta(microseconds=1)
            return dt
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
    
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
            return self.get_minute_summary(ts_code, period_type, hours)
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
            latest_data = self.get_minute_latest_data(ts_code, '1min', 1)
            
            if latest_data.empty:
                return {
                    'success': False,
                    'message': f'未找到 {ts_code} 的实时数据',
                    'data': None
                }

            latest_row = latest_data.iloc[0]
            
            return {
                'success': True,
                'message': '获取成功',
                'data': {
                    'ts_code': latest_row.ts_code,
                    'current_price': latest_row.close,
                    'change': latest_row.change,
                    'pct_chg': latest_row.pct_chg,
                    'volume': latest_row.volume,
                    'amount': latest_row.amount,
                    'update_time': latest_row.datetime.isoformat(),
                    'open': latest_row.open,
                    'high': latest_row.high,
                    'low': latest_row.low
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
            latest_data = self.get_minute_reader().get_data(period_type='1min')
            if latest_data.empty:
                return {
                    'success': False,
                    'message': '没有找到市场数据',
                    'data': None
                }

            latest_time = pd.to_datetime(latest_data["datetime"]).max()
            window_start = latest_time - timedelta(minutes=5)
            window_data = latest_data[latest_data["datetime"] >= window_start]

            if window_data.empty:
                return {
                    'success': False,
                    'message': '没有找到最新市场数据',
                    'data': None
                }

            # 统计市场数据
            total_stocks = len(window_data)
            rising_stocks = len(window_data[window_data["pct_chg"] > 0])
            falling_stocks = len(window_data[window_data["pct_chg"] < 0])
            flat_stocks = total_stocks - rising_stocks - falling_stocks

            total_volume = window_data["volume"].fillna(0).sum()
            total_amount = window_data["amount"].fillna(0).sum()
            avg_pct_chg = window_data["pct_chg"].dropna().mean()
            
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
                    'avg_pct_chg': round(avg_pct_chg, 2) if pd.notna(avg_pct_chg) else 0
                }
            }
            
        except Exception as e:
            logger.error(f"获取市场概览失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}',
                'data': None
            } 

    def get_minute_reader(self) -> MinuteParquetReader:
        return self.data_reader.get_minute_reader()

    def get_minute_latest_data(self, ts_code: str, period_type: str = '1min', limit: int = 100) -> pd.DataFrame:
        return self.get_minute_reader().get_latest_data(ts_code, period_type, limit)

    def get_minute_range_data(
        self,
        ts_code: str,
        start_time,
        end_time,
        period_type: str = '1min'
    ) -> pd.DataFrame:
        return self.get_minute_reader().get_data(ts_code=ts_code, period_type=period_type, start_time=start_time, end_time=end_time)

    def get_minute_summary(self, ts_code: str, period_type: str = '1min', hours: int = 24) -> Dict:
        return self.get_minute_reader().get_summary(ts_code, period_type, hours)

    def get_minute_periods(self) -> List[str]:
        return ['1min', '5min', '15min', '30min', '60min']

    def get_available_minute_stocks(self) -> List[str]:
        df = self.get_minute_reader().get_data(period_type=None)
        if df.empty or "ts_code" not in df.columns:
            return []
        return sorted(df["ts_code"].dropna().astype(str).unique().tolist())

    def get_minute_stats(self) -> Dict:
        periods = self.get_minute_periods()
        stats: Dict[str, int] = {}
        all_frames: list[pd.DataFrame] = []
        for period in periods:
            df = self.get_minute_reader().get_data(period_type=period)
            stats[period] = int(len(df))
            if not df.empty:
                all_frames.append(df)

        if not all_frames:
            return {
                'period_stats': stats,
                'total_stocks': 0,
                'latest_time': None,
                'earliest_time': None,
                'total_records': 0,
            }

        combined = pd.concat(all_frames, ignore_index=True)
        latest_time = pd.to_datetime(combined["datetime"]).max()
        earliest_time = pd.to_datetime(combined["datetime"]).min()
        total_stocks = int(combined["ts_code"].dropna().astype(str).nunique()) if "ts_code" in combined.columns else 0
        return {
            'period_stats': stats,
            'total_stocks': total_stocks,
            'latest_time': latest_time.isoformat() if pd.notna(latest_time) else None,
            'earliest_time': earliest_time.isoformat() if pd.notna(earliest_time) else None,
            'total_records': int(len(combined)),
        }
