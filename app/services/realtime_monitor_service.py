"""
实时监控服务
提供实时行情监控、热点板块监控、异动股票监控和市场情绪监控功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

from app.services.data_reader import ParquetDataReader

logger = logging.getLogger(__name__)


class RealtimeMonitorService:
    """实时监控服务"""
    DEFAULT_PERIOD_TYPE = "5min"
    
    def __init__(self):
        self.data_reader = ParquetDataReader()
        self.minute_reader = self.data_reader.get_minute_reader()
        # 板块映射依赖 data_reader 的 stock_basic，必须在它初始化之后构建
        self.sector_mapping = self._initialize_sector_mapping()
    
    def _initialize_sector_mapping(self):
        """初始化板块映射：优先用 stock_basic 的真实行业字段。

        旧实现是 28 个手工挑选的 4 股列表，存在大量错分
        （如五粮液在"医药"、海康威司重复在"电子"和"通信"），
        计算出的"板块表现"不可信。
        """
        fallback = {
            '银行': ['000001.SZ', '600000.SH', '600036.SH', '601988.SH'],
            '食品饮料': ['000568.SZ', '600519.SH', '000596.SZ', '600887.SH'],
            '电子': ['000725.SZ', '002415.SH', '600584.SH', '000021.SZ'],
        }
        try:
            stock_basic = self.data_reader.get_stock_basic()
            if stock_basic.empty or "industry" not in stock_basic.columns:
                logger.warning("stock_basic 缺少行业字段，板块映射退化为默认列表")
                return fallback
            df = stock_basic.dropna(subset=["industry", "ts_code"])
            mapping = {}
            for industry, group in df.groupby("industry"):
                mapping[str(industry)] = group["ts_code"].astype(str).tolist()
            if not mapping:
                return fallback
            return mapping
        except Exception as e:
            logger.error(f"构建板块映射失败，退化为默认列表: {e}")
            return fallback

    def _minute_frame(
        self,
        period_type: str = DEFAULT_PERIOD_TYPE,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        ts_codes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load minute rows from parquet and optionally filter by codes."""
        df = self.minute_reader.get_data(
            period_type=period_type,
            start_time=start_time,
            end_time=end_time,
        )
        if df.empty:
            return df
        if ts_codes:
            df = df[df["ts_code"].isin(set(ts_codes))]
        return df

    @staticmethod
    def _latest_rows(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "datetime" not in df.columns or "ts_code" not in df.columns:
            return pd.DataFrame()
        return (
            df.sort_values("datetime")
            .groupby("ts_code", as_index=False, sort=False)
            .tail(1)
            .reset_index(drop=True)
        )
    
    def get_realtime_quotes(self, stock_codes: List[str] = None, 
                           period_type: str = DEFAULT_PERIOD_TYPE, limit: int = 50) -> Dict:
        """获取实时行情数据"""
        try:
            # 如果没有指定股票代码，获取活跃股票
            if not stock_codes:
                stock_codes = self._get_active_stocks(limit)
            
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)  # 最近1小时
            minute_df = self._minute_frame(period_type=period_type, start_time=start_time, end_time=end_time, ts_codes=stock_codes)
            latest_rows = self._latest_rows(minute_df)

            # 一次批量预取 昨收/换手率，避免每只股票各读一遍全量数据
            current_date = end_time.strftime('%Y%m%d')
            prev_close_map = self._daily_prev_close_map(stock_codes, current_date)
            turnover_map = self._daily_turnover_map(stock_codes, current_date)

            quotes = []
            for _, latest_data in latest_rows.iterrows():
                ts_code = latest_data["ts_code"]
                try:
                    current_time = pd.to_datetime(latest_data["datetime"]).to_pydatetime()
                    prev_close = self._get_previous_close(ts_code, current_time, period_type, prev_close_map)

                    change_pct = 0.0
                    if prev_close and prev_close > 0:
                        change_pct = (latest_data["close"] - prev_close) / prev_close * 100

                    volume_ratio = self._calculate_volume_ratio(ts_code, current_time, period_type)

                    quotes.append({
                        'ts_code': ts_code,
                        'name': self._get_stock_name(ts_code),
                        'current_price': latest_data["close"],
                        'open_price': latest_data["open"],
                        'high_price': latest_data["high"],
                        'low_price': latest_data["low"],
                        'volume': latest_data["volume"],
                        'amount': latest_data["amount"],
                        'change_pct': change_pct,
                        'volume_ratio': volume_ratio,
                        'update_time': current_time.isoformat(),
                        'turnover_rate': self._calculate_turnover_rate(ts_code, latest_data["volume"], turnover_map)
                    })
                except Exception as e:
                    logger.error(f"获取 {ts_code} 行情数据失败: {str(e)}")
                    continue
            
            return {
                'success': True,
                'data': {
                    'quotes': quotes,
                    'total_count': len(quotes),
                    'update_time': datetime.now().isoformat()
                },
                'message': f'成功获取 {len(quotes)} 只股票的实时行情'
            }
            
        except Exception as e:
            logger.error(f"获取实时行情失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_sector_performance(self, period_hours: int = 1) -> Dict:
        """获取板块表现"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=period_hours)
            minute_df = self._minute_frame(period_type=self.DEFAULT_PERIOD_TYPE, start_time=start_time, end_time=end_time)
            latest_rows = self._latest_rows(minute_df)

            if latest_rows.empty:
                return {
                    'success': True,
                    'data': {
                        'sectors': [],
                        'total_sectors': 0,
                        'period_hours': period_hours,
                        'update_time': datetime.now().isoformat()
                    },
                    'message': '当前时段无分钟数据'
                }

            sector_performance = []

            # 批量预取昨收，避免逐股逐板块重复读全量数据
            sector_codes = list(set(latest_rows["ts_code"].astype(str)))
            prev_close_map = self._daily_prev_close_map(sector_codes, end_time.strftime('%Y%m%d'))

            for sector_name, stock_codes in self.sector_mapping.items():
                try:
                    sector_rows = latest_rows[latest_rows["ts_code"].isin(stock_codes)].copy()
                    if sector_rows.empty:
                        continue

                    sector_changes = []
                    sector_volumes = []
                    sector_amounts = []

                    for _, latest_data in sector_rows.iterrows():
                        current_time = pd.to_datetime(latest_data["datetime"]).to_pydatetime()
                        prev_close = self._get_previous_close(latest_data["ts_code"], current_time, self.DEFAULT_PERIOD_TYPE, prev_close_map)
                        if prev_close and prev_close > 0:
                            change_pct = (latest_data["close"] - prev_close) / prev_close * 100
                            sector_changes.append(change_pct)
                            sector_volumes.append(latest_data["volume"])
                            sector_amounts.append(latest_data["amount"])
                    
                    if sector_changes:
                        # 计算板块平均涨跌幅（等权重）
                        avg_change = np.mean(sector_changes)
                        total_volume = sum(sector_volumes)
                        total_amount = sum(sector_amounts)
                        
                        # 计算上涨股票数量
                        rising_count = sum(1 for change in sector_changes if change > 0)
                        falling_count = sum(1 for change in sector_changes if change < 0)
                        
                        sector_performance.append({
                            'sector_name': sector_name,
                            'avg_change_pct': avg_change,
                            'total_volume': total_volume,
                            'total_amount': total_amount,
                            'stock_count': len(sector_changes),
                            'rising_count': rising_count,
                            'falling_count': falling_count,
                            'rising_ratio': rising_count / len(sector_changes) * 100 if sector_changes else 0
                        })
                        
                except Exception as e:
                    logger.error(f"计算板块 {sector_name} 表现失败: {str(e)}")
                    continue
            
            # 按涨跌幅排序
            sector_performance.sort(key=lambda x: x['avg_change_pct'], reverse=True)
            
            return {
                'success': True,
                'data': {
                    'sectors': sector_performance,
                    'total_sectors': len(sector_performance),
                    'period_hours': period_hours,
                    'update_time': datetime.now().isoformat()
                },
                'message': f'成功获取 {len(sector_performance)} 个板块的表现数据'
            }
            
        except Exception as e:
            logger.error(f"获取板块表现失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def detect_anomalies(self, change_threshold: float = 5.0, 
                        volume_threshold: float = 3.0, 
                        period_hours: int = 1) -> Dict:
        """检测异动股票"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=period_hours)
            active_stocks = self._get_active_stocks(200)
            minute_df = self._minute_frame(period_type=self.DEFAULT_PERIOD_TYPE, start_time=start_time, end_time=end_time, ts_codes=active_stocks)
            latest_rows = self._latest_rows(minute_df)
            
            anomalies = []
            
            for _, latest_data in latest_rows.iterrows():
                ts_code = latest_data["ts_code"]
                try:
                    current_time = pd.to_datetime(latest_data["datetime"]).to_pydatetime()
                    prev_close = self._get_previous_close(ts_code, current_time, self.DEFAULT_PERIOD_TYPE)
                    if not prev_close or prev_close <= 0:
                        continue

                    change_pct = (latest_data["close"] - prev_close) / prev_close * 100
                    volume_ratio = self._calculate_volume_ratio(ts_code, current_time, self.DEFAULT_PERIOD_TYPE)

                    anomaly_types = []
                    if abs(change_pct) >= change_threshold:
                        anomaly_types.append('急涨' if change_pct > 0 else '急跌')
                    if volume_ratio >= volume_threshold:
                        anomaly_types.append('放量')
                    if self._check_price_breakout(ts_code, latest_data):
                        anomaly_types.append('突破')

                    if anomaly_types:
                        anomalies.append({
                            'ts_code': ts_code,
                            'name': self._get_stock_name(ts_code),
                            'current_price': latest_data["close"],
                            'change_pct': change_pct,
                            'volume_ratio': volume_ratio,
                            'anomaly_types': anomaly_types,
                            'anomaly_score': self._calculate_anomaly_score(change_pct, volume_ratio),
                            'update_time': current_time.isoformat()
                        })
                except Exception as e:
                    logger.error(f"检测 {ts_code} 异动失败: {str(e)}")
                    continue
            
            # 按异动评分排序
            anomalies.sort(key=lambda x: x['anomaly_score'], reverse=True)
            
            return {
                'success': True,
                'data': {
                    'anomalies': anomalies[:50],  # 返回前50个异动股票
                    'total_count': len(anomalies),
                    'change_threshold': change_threshold,
                    'volume_threshold': volume_threshold,
                    'period_hours': period_hours,
                    'update_time': datetime.now().isoformat()
                },
                'message': f'检测到 {len(anomalies)} 只异动股票'
            }
            
        except Exception as e:
            logger.error(f"检测异动股票失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_market_sentiment(self, period_hours: int = 1) -> Dict:
        """获取市场情绪指标"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=period_hours)
            active_stocks = self._get_active_stocks(500)
            minute_df = self._minute_frame(period_type=self.DEFAULT_PERIOD_TYPE, start_time=start_time, end_time=end_time, ts_codes=active_stocks)
            latest_rows = self._latest_rows(minute_df)
            
            rising_stocks = 0
            falling_stocks = 0
            unchanged_stocks = 0
            total_volume = 0
            total_amount = 0
            changes = []
            
            for _, latest_data in latest_rows.iterrows():
                try:
                    current_time = pd.to_datetime(latest_data["datetime"]).to_pydatetime()
                    prev_close = self._get_previous_close(latest_data["ts_code"], current_time, self.DEFAULT_PERIOD_TYPE)
                    if not prev_close or prev_close <= 0:
                        continue

                    change_pct = (latest_data["close"] - prev_close) / prev_close * 100
                    changes.append(change_pct)

                    if change_pct > 0.1:
                        rising_stocks += 1
                    elif change_pct < -0.1:
                        falling_stocks += 1
                    else:
                        unchanged_stocks += 1

                    total_volume += latest_data["volume"]
                    total_amount += latest_data["amount"]
                except Exception as e:
                    logger.error(f"处理 {latest_data['ts_code']} 市场情绪数据失败: {str(e)}")
                    continue
            
            total_stocks = rising_stocks + falling_stocks + unchanged_stocks
            
            if total_stocks == 0:
                return {
                    'success': False,
                    'message': '没有足够的数据计算市场情绪'
                }
            
            # 计算市场情绪指标
            rising_ratio = rising_stocks / total_stocks * 100
            falling_ratio = falling_stocks / total_stocks * 100
            
            # 计算市场强度指标
            avg_change = np.mean(changes) if changes else 0
            change_std = np.std(changes) if changes else 0
            
            # 计算情绪评分 (0-100)
            sentiment_score = min(100, max(0, 50 + avg_change * 5 + (rising_ratio - 50)))
            
            # 确定市场状态
            if sentiment_score >= 70:
                market_status = '强势'
                status_color = 'success'
            elif sentiment_score >= 55:
                market_status = '偏强'
                status_color = 'info'
            elif sentiment_score >= 45:
                market_status = '震荡'
                status_color = 'warning'
            elif sentiment_score >= 30:
                market_status = '偏弱'
                status_color = 'secondary'
            else:
                market_status = '弱势'
                status_color = 'danger'
            
            return {
                'success': True,
                'data': {
                    'sentiment_score': sentiment_score,
                    'market_status': market_status,
                    'status_color': status_color,
                    'rising_stocks': rising_stocks,
                    'falling_stocks': falling_stocks,
                    'unchanged_stocks': unchanged_stocks,
                    'total_stocks': total_stocks,
                    'rising_ratio': rising_ratio,
                    'falling_ratio': falling_ratio,
                    'avg_change_pct': avg_change,
                    'volatility': change_std,
                    'total_volume': total_volume,
                    'total_amount': total_amount,
                    'period_hours': period_hours,
                    'update_time': datetime.now().isoformat()
                },
                'message': f'成功计算市场情绪，涉及 {total_stocks} 只股票'
            }
            
        except Exception as e:
            logger.error(f"获取市场情绪失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_monitor_overview(self) -> Dict:
        """获取监控概览"""
        try:
            minute_df = self._minute_frame(period_type=self.DEFAULT_PERIOD_TYPE)
            if minute_df.empty:
                return {
                    'success': True,
                    'data': {
                        'total_stocks': 0,
                        'active_stocks': 0,
                        'today_records': 0,
                        'latest_update': None,
                        'system_status': 'running',
                        'data_delay': None
                    },
                    'message': '监控概览获取成功'
                }

            minute_df["datetime"] = pd.to_datetime(minute_df["datetime"], errors="coerce")
            total_stocks = int(minute_df["ts_code"].dropna().astype(str).nunique()) if "ts_code" in minute_df.columns else 0
            latest_time = minute_df["datetime"].max()
            today = datetime.now().date()
            today_records = int((minute_df["datetime"].dt.date == today).sum())
            recent_time = datetime.now() - timedelta(hours=1)
            active_stocks = int(minute_df[minute_df["datetime"] >= recent_time]["ts_code"].dropna().astype(str).nunique())
            
            return {
                'success': True,
                'data': {
                    'total_stocks': total_stocks,
                    'active_stocks': active_stocks,
                    'today_records': today_records,
                    'latest_update': latest_time.isoformat() if latest_time else None,
                    'system_status': 'running',
                    'data_delay': self._calculate_data_delay(latest_time) if latest_time else None
                },
                'message': '监控概览获取成功'
            }
            
        except Exception as e:
            logger.error(f"获取监控概览失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _get_active_stocks(self, limit: int = 100) -> List[str]:
        """获取活跃股票列表"""
        try:
            recent_time = datetime.now() - timedelta(hours=1)
            minute_df = self._minute_frame(period_type=self.DEFAULT_PERIOD_TYPE, start_time=recent_time, end_time=datetime.now())
            if minute_df.empty or "ts_code" not in minute_df.columns:
                return ['000001.SZ', '000002.SZ', '600000.SH', '600036.SH', '000858.SZ']
            return minute_df["ts_code"].dropna().astype(str).drop_duplicates().head(limit).tolist()
            
        except Exception as e:
            logger.error(f"获取活跃股票失败: {str(e)}")
            # 返回默认股票列表
            return ['000001.SZ', '000002.SZ', '600000.SH', '600036.SH', '000858.SZ']
    
    def _daily_prev_close_map(self, ts_codes: List[str], current_date: str,
                              lookback_days: int = 20) -> Dict[str, float]:
        """批量获取昨收：一次读日线，返回 {ts_code: 昨收}。

        当日 bar 的 pre_close 就是昨收；当日尚无日线（盘中）时，
        取最近一根前日 bar 的 close。
        """
        result: Dict[str, float] = {}
        try:
            if not ts_codes:
                return result
            start = (datetime.strptime(current_date, '%Y%m%d') - timedelta(days=lookback_days)).strftime('%Y%m%d')
            daily = self.data_reader.get_daily(ts_codes=list(ts_codes), start_date=start)
            if daily.empty or "ts_code" not in daily.columns:
                return result
            daily = daily.copy()
            if "trade_date" in daily.columns:
                daily["td"] = daily["trade_date"].astype(str).str.replace("-", "", regex=False)
            else:
                return result
            daily = daily.sort_values(["ts_code", "td"])
            for ts_code, group in daily.groupby("ts_code"):
                prior_or_same = group[group["td"] <= current_date]
                if prior_or_same.empty:
                    continue
                last = prior_or_same.iloc[-1]
                if last["td"] == current_date and "pre_close" in group.columns:
                    pc = last.get("pre_close")
                    if pc is not None and not pd.isna(pc) and float(pc) > 0:
                        result[str(ts_code)] = float(pc)
                        continue
                close = last.get("close")
                if close is not None and not pd.isna(close) and float(close) > 0:
                    result[str(ts_code)] = float(close)
            return result
        except Exception as e:
            logger.error(f"批量获取昨收失败: {e}")
            return result

    def _daily_turnover_map(self, ts_codes: List[str], current_date: str,
                            lookback_days: int = 10) -> Dict[str, float]:
        """批量获取最近可得的真实换手率（来自 daily_basic），缺数据返回空映射。"""
        result: Dict[str, float] = {}
        try:
            if not ts_codes:
                return result
            start = (datetime.strptime(current_date, '%Y%m%d') - timedelta(days=lookback_days)).strftime('%Y%m%d')
            basic = self.data_reader.get_daily_basic(ts_codes=list(ts_codes), start_date=start)
            if basic.empty or "ts_code" not in basic.columns or "turnover_rate" not in basic.columns:
                return result
            basic = basic.copy()
            basic["td"] = basic["trade_date"].astype(str).str.replace("-", "", regex=False)
            basic = basic[basic["td"] <= current_date].sort_values(["ts_code", "td"])
            for ts_code, group in basic.groupby("ts_code"):
                last = group.iloc[-1]
                value = last.get("turnover_rate")
                if value is not None and not pd.isna(value):
                    result[str(ts_code)] = float(value)
            return result
        except Exception as e:
            logger.error(f"批量获取换手率失败: {e}")
            return result

    def _get_previous_close(self, ts_code: str, current_time: datetime, period_type: str,
                            prev_close_map: Optional[Dict[str, float]] = None) -> Optional[float]:
        """获取昨收价（前一交易日收盘价）。

        优先用预取的日线 昨收 map（当日 pre_close 或最近前日 close）；
        无日线数据时退回分钟序列的最近收盘（此时返回值语义是
        "最近一次分钟收盘"而非严格昨收，调用方需容忍）。
        """
        try:
            if prev_close_map and ts_code in prev_close_map:
                return prev_close_map[ts_code]

            current_date = current_time.strftime('%Y%m%d')
            daily_map = self._daily_prev_close_map([ts_code], current_date)
            if ts_code in daily_map:
                return daily_map[ts_code]

            # 日线缺失时的退化路径：最近一根分钟 bar 的 close
            df = self._minute_frame(period_type=period_type, end_time=current_time, ts_codes=[ts_code])
            if df.empty:
                return None
            latest = self._latest_rows(df)
            if latest.empty:
                return None
            return float(latest.iloc[0]["close"])

        except Exception as e:
            logger.error(f"获取 {ts_code} 前收盘价失败: {str(e)}")
            return None
    
    def _calculate_volume_ratio(self, ts_code: str, current_time: datetime, period_type: str) -> float:
        """计算成交量比"""
        try:
            start_time = current_time - timedelta(hours=20)
            df = self._minute_frame(period_type=period_type, start_time=start_time, end_time=current_time, ts_codes=[ts_code])
            if df.empty:
                return 1.0

            avg_volume = df["volume"].dropna().mean()
            if pd.isna(avg_volume) or avg_volume == 0:
                return 1.0

            current_rows = df[df["datetime"] == current_time]
            if current_rows.empty:
                latest = self._latest_rows(df)
                if latest.empty:
                    return 1.0
                current_volume = latest.iloc[0]["volume"]
            else:
                current_volume = current_rows.iloc[0]["volume"]

            return float(current_volume) / float(avg_volume)
            
        except Exception as e:
            logger.error(f"计算 {ts_code} 成交量比失败: {str(e)}")
            return 1.0
    
    def _calculate_turnover_rate(self, ts_code: str, volume: float,
                                 turnover_map: Optional[Dict[str, float]] = None) -> Optional[float]:
        """换手率：来自 daily_basic 的真实值；无数据时返回 None 而不是编造。

        旧实现 `min(20.0, volume/1000000*0.1)` 是拍脑袋的估算值，
        却以真实数据的形态展示给用户，对量化产品不可接受。
        """
        if turnover_map and ts_code in turnover_map:
            return turnover_map[ts_code]

        try:
            current_date = datetime.now().strftime('%Y%m%d')
            daily_map = self._daily_turnover_map([ts_code], current_date)
            return daily_map.get(ts_code)
        except Exception as e:
            logger.error(f"获取 {ts_code} 换手率失败: {str(e)}")
            return None
    
    def _get_stock_name(self, ts_code: str) -> str:
        """获取股票名称"""
        try:
            stock_basic = self.data_reader.get_stock_basic(ts_code)
            if stock_basic.empty or "name" not in stock_basic.columns:
                return ts_code
            return str(stock_basic.iloc[0]["name"])
        except Exception as e:
            logger.error(f"获取 {ts_code} 股票名称失败: {str(e)}")
            return ts_code
    
    def _check_price_breakout(self, ts_code: str, latest_data) -> bool:
        """检查价格突破（简化版本）"""
        try:
            latest_time = pd.to_datetime(latest_data["datetime"]).to_pydatetime()
            start_time = latest_time - timedelta(hours=20)
            price_df = self._minute_frame(period_type=self.DEFAULT_PERIOD_TYPE, start_time=start_time, end_time=latest_time, ts_codes=[ts_code])

            if price_df.empty:
                return False

            price_df = price_df[price_df["datetime"] < latest_time]
            if price_df.empty:
                return False

            max_high = price_df["high"].max()
            min_low = price_df["low"].min()
            if pd.isna(max_high) or pd.isna(min_low):
                return False

            return (latest_data["high"] > max_high * 1.01 or latest_data["low"] < min_low * 0.99)
            
        except Exception as e:
            logger.error(f"检查 {ts_code} 价格突破失败: {str(e)}")
            return False
    
    def _calculate_anomaly_score(self, change_pct: float, volume_ratio: float) -> float:
        """计算异动评分"""
        try:
            # 综合价格变动和成交量变动计算异动评分
            price_score = min(50, abs(change_pct) * 5)  # 价格变动评分
            volume_score = min(50, (volume_ratio - 1) * 10)  # 成交量变动评分
            
            return price_score + volume_score
            
        except Exception as e:
            logger.error(f"计算异动评分失败: {str(e)}")
            return 0.0
    
    def _calculate_data_delay(self, latest_time: datetime) -> int:
        """计算数据延迟（分钟）"""
        try:
            now = datetime.now()
            delay = (now - latest_time).total_seconds() / 60
            return int(delay)
        except Exception as e:
            logger.error(f"计算数据延迟失败: {str(e)}")
            return 0 
