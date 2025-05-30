"""
实时监控服务
提供实时行情监控、热点板块监控、异动股票监控和市场情绪监控功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from sqlalchemy import func, desc, asc

from app.models.stock_minute_data import StockMinuteData
from app.models.stock_basic import StockBasic
from app.models.realtime_indicator import RealtimeIndicator

logger = logging.getLogger(__name__)


class RealtimeMonitorService:
    """实时监控服务"""
    
    def __init__(self):
        self.sector_mapping = self._initialize_sector_mapping()
    
    def _initialize_sector_mapping(self):
        """初始化板块映射"""
        return {
            '银行': ['000001.SZ', '600000.SH', '600036.SH', '601988.SH'],
            '房地产': ['000002.SZ', '600048.SH', '000069.SZ', '600383.SH'],
            '钢铁': ['600019.SH', '000898.SZ', '600581.SH', '000709.SZ'],
            '煤炭': ['600188.SH', '601088.SH', '000983.SZ', '600123.SH'],
            '有色金属': ['600362.SH', '000831.SZ', '002460.SZ', '600111.SH'],
            '石油石化': ['600028.SH', '000656.SZ', '600688.SH', '000301.SZ'],
            '电力': ['600886.SH', '000027.SZ', '600795.SH', '000875.SZ'],
            '汽车': ['600104.SH', '000625.SZ', '002594.SZ', '600066.SH'],
            '机械': ['000157.SZ', '002008.SZ', '600031.SH', '000528.SZ'],
            '电子': ['000725.SZ', '002415.SZ', '600584.SH', '000021.SZ'],
            '医药': ['000858.SZ', '600276.SH', '000423.SZ', '600867.SH'],
            '食品饮料': ['000568.SZ', '600519.SH', '000596.SZ', '600887.SH'],
            '纺织服装': ['600177.SH', '002029.SZ', '000902.SZ', '600398.SH'],
            '轻工制造': ['000488.SZ', '002572.SZ', '600978.SH', '000726.SZ'],
            '商贸零售': ['600694.SH', '000759.SZ', '002024.SZ', '600361.SH'],
            '交通运输': ['600026.SH', '000089.SZ', '600115.SH', '000039.SZ'],
            '休闲服务': ['000978.SZ', '600138.SH', '000430.SZ', '600258.SH'],
            '综合': ['600643.SH', '000039.SZ', '600663.SH', '000042.SZ'],
            '建筑材料': ['000401.SZ', '600585.SH', '000877.SZ', '600801.SH'],
            '建筑装饰': ['000090.SZ', '002271.SZ', '600170.SH', '000065.SZ'],
            '电气设备': ['000400.SZ', '002202.SZ', '600406.SH', '000012.SZ'],
            '国防军工': ['000768.SZ', '002013.SZ', '600150.SH', '000099.SZ'],
            '计算机': ['000977.SZ', '002405.SZ', '600588.SH', '000034.SZ'],
            '传媒': ['000156.SZ', '002027.SZ', '600633.SH', '000917.SZ'],
            '通信': ['000063.SZ', '002415.SZ', '600050.SH', '000070.SZ'],
            '公用事业': ['000826.SZ', '600008.SH', '000939.SZ', '600874.SH'],
            '农林牧渔': ['000876.SZ', '002714.SZ', '600598.SH', '000735.SZ'],
            '化工': ['000792.SZ', '002648.SZ', '600309.SH', '000059.SZ'],
            '非银金融': ['000166.SZ', '002736.SZ', '600030.SH', '000776.SZ']
        }
    
    def get_realtime_quotes(self, stock_codes: List[str] = None, 
                           period_type: str = '1min', limit: int = 50) -> Dict:
        """获取实时行情数据"""
        try:
            # 如果没有指定股票代码，获取活跃股票
            if not stock_codes:
                stock_codes = self._get_active_stocks(limit)
            
            # 获取最新价格数据
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)  # 最近1小时
            
            quotes = []
            for ts_code in stock_codes:
                try:
                    # 获取最新数据
                    latest_data = StockMinuteData.query.filter(
                        StockMinuteData.ts_code == ts_code,
                        StockMinuteData.period_type == period_type,
                        StockMinuteData.datetime >= start_time
                    ).order_by(desc(StockMinuteData.datetime)).first()
                    
                    if not latest_data:
                        continue
                    
                    # 获取前一交易日收盘价（用于计算涨跌幅）
                    prev_close = self._get_previous_close(ts_code, latest_data.datetime, period_type)
                    
                    # 计算涨跌幅
                    change_pct = 0.0
                    if prev_close and prev_close > 0:
                        change_pct = (latest_data.close - prev_close) / prev_close * 100
                    
                    # 计算成交量比
                    volume_ratio = self._calculate_volume_ratio(ts_code, latest_data.datetime, period_type)
                    
                    quotes.append({
                        'ts_code': ts_code,
                        'name': self._get_stock_name(ts_code),
                        'current_price': latest_data.close,
                        'open_price': latest_data.open,
                        'high_price': latest_data.high,
                        'low_price': latest_data.low,
                        'volume': latest_data.volume,
                        'amount': latest_data.amount,
                        'change_pct': change_pct,
                        'volume_ratio': volume_ratio,
                        'update_time': latest_data.datetime.isoformat(),
                        'turnover_rate': self._calculate_turnover_rate(ts_code, latest_data.volume)
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
            
            sector_performance = []
            
            for sector_name, stock_codes in self.sector_mapping.items():
                try:
                    sector_changes = []
                    sector_volumes = []
                    sector_amounts = []
                    
                    for ts_code in stock_codes:
                        # 获取最新数据
                        latest_data = StockMinuteData.query.filter(
                            StockMinuteData.ts_code == ts_code,
                            StockMinuteData.datetime >= start_time
                        ).order_by(desc(StockMinuteData.datetime)).first()
                        
                        if not latest_data:
                            continue
                        
                        # 计算涨跌幅
                        prev_close = self._get_previous_close(ts_code, latest_data.datetime, '1min')
                        if prev_close and prev_close > 0:
                            change_pct = (latest_data.close - prev_close) / prev_close * 100
                            sector_changes.append(change_pct)
                            sector_volumes.append(latest_data.volume)
                            sector_amounts.append(latest_data.amount)
                    
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
            
            # 获取所有活跃股票
            active_stocks = self._get_active_stocks(200)
            
            anomalies = []
            
            for ts_code in active_stocks:
                try:
                    # 获取最新数据
                    latest_data = StockMinuteData.query.filter(
                        StockMinuteData.ts_code == ts_code,
                        StockMinuteData.datetime >= start_time
                    ).order_by(desc(StockMinuteData.datetime)).first()
                    
                    if not latest_data:
                        continue
                    
                    # 计算涨跌幅
                    prev_close = self._get_previous_close(ts_code, latest_data.datetime, '1min')
                    if not prev_close or prev_close <= 0:
                        continue
                    
                    change_pct = (latest_data.close - prev_close) / prev_close * 100
                    
                    # 计算成交量比
                    volume_ratio = self._calculate_volume_ratio(ts_code, latest_data.datetime, '1min')
                    
                    # 检测异动条件
                    anomaly_types = []
                    
                    # 价格异动
                    if abs(change_pct) >= change_threshold:
                        if change_pct > 0:
                            anomaly_types.append('急涨')
                        else:
                            anomaly_types.append('急跌')
                    
                    # 成交量异动
                    if volume_ratio >= volume_threshold:
                        anomaly_types.append('放量')
                    
                    # 价格突破（简单判断）
                    if self._check_price_breakout(ts_code, latest_data):
                        anomaly_types.append('突破')
                    
                    if anomaly_types:
                        anomalies.append({
                            'ts_code': ts_code,
                            'name': self._get_stock_name(ts_code),
                            'current_price': latest_data.close,
                            'change_pct': change_pct,
                            'volume_ratio': volume_ratio,
                            'anomaly_types': anomaly_types,
                            'anomaly_score': self._calculate_anomaly_score(change_pct, volume_ratio),
                            'update_time': latest_data.datetime.isoformat()
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
            
            # 获取所有活跃股票的数据
            active_stocks = self._get_active_stocks(500)
            
            rising_stocks = 0
            falling_stocks = 0
            unchanged_stocks = 0
            total_volume = 0
            total_amount = 0
            changes = []
            
            for ts_code in active_stocks:
                try:
                    # 获取最新数据
                    latest_data = StockMinuteData.query.filter(
                        StockMinuteData.ts_code == ts_code,
                        StockMinuteData.datetime >= start_time
                    ).order_by(desc(StockMinuteData.datetime)).first()
                    
                    if not latest_data:
                        continue
                    
                    # 计算涨跌幅
                    prev_close = self._get_previous_close(ts_code, latest_data.datetime, '1min')
                    if not prev_close or prev_close <= 0:
                        continue
                    
                    change_pct = (latest_data.close - prev_close) / prev_close * 100
                    changes.append(change_pct)
                    
                    # 统计涨跌家数
                    if change_pct > 0.1:
                        rising_stocks += 1
                    elif change_pct < -0.1:
                        falling_stocks += 1
                    else:
                        unchanged_stocks += 1
                    
                    total_volume += latest_data.volume
                    total_amount += latest_data.amount
                    
                except Exception as e:
                    logger.error(f"处理 {ts_code} 市场情绪数据失败: {str(e)}")
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
            # 获取基础统计
            total_stocks = StockMinuteData.query.with_entities(
                func.count(func.distinct(StockMinuteData.ts_code))
            ).scalar() or 0
            
            # 获取最新更新时间
            latest_time = StockMinuteData.query.with_entities(
                func.max(StockMinuteData.datetime)
            ).scalar()
            
            # 获取今日数据量
            today = datetime.now().date()
            today_records = StockMinuteData.query.filter(
                func.date(StockMinuteData.datetime) == today
            ).count()
            
            # 获取活跃股票数（最近1小时有数据）
            recent_time = datetime.now() - timedelta(hours=1)
            active_stocks = StockMinuteData.query.filter(
                StockMinuteData.datetime >= recent_time
            ).with_entities(
                func.count(func.distinct(StockMinuteData.ts_code))
            ).scalar() or 0
            
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
            # 获取最近1小时有数据的股票
            recent_time = datetime.now() - timedelta(hours=1)
            
            active_stocks = StockMinuteData.query.filter(
                StockMinuteData.datetime >= recent_time
            ).with_entities(
                StockMinuteData.ts_code
            ).distinct().limit(limit).all()
            
            return [stock[0] for stock in active_stocks]
            
        except Exception as e:
            logger.error(f"获取活跃股票失败: {str(e)}")
            # 返回默认股票列表
            return ['000001.SZ', '000002.SZ', '600000.SH', '600036.SH', '000858.SZ']
    
    def _get_previous_close(self, ts_code: str, current_time: datetime, period_type: str) -> Optional[float]:
        """获取前一交易日收盘价"""
        try:
            # 简化处理：获取当前时间前1小时的数据作为基准
            prev_time = current_time - timedelta(hours=1)
            
            prev_data = StockMinuteData.query.filter(
                StockMinuteData.ts_code == ts_code,
                StockMinuteData.period_type == period_type,
                StockMinuteData.datetime <= prev_time
            ).order_by(desc(StockMinuteData.datetime)).first()
            
            return prev_data.close if prev_data else None
            
        except Exception as e:
            logger.error(f"获取 {ts_code} 前收盘价失败: {str(e)}")
            return None
    
    def _calculate_volume_ratio(self, ts_code: str, current_time: datetime, period_type: str) -> float:
        """计算成交量比"""
        try:
            # 获取最近20个周期的平均成交量
            start_time = current_time - timedelta(hours=20)
            
            avg_volume = StockMinuteData.query.filter(
                StockMinuteData.ts_code == ts_code,
                StockMinuteData.period_type == period_type,
                StockMinuteData.datetime >= start_time,
                StockMinuteData.datetime < current_time
            ).with_entities(
                func.avg(StockMinuteData.volume)
            ).scalar()
            
            if not avg_volume or avg_volume == 0:
                return 1.0
            
            # 获取当前成交量
            current_data = StockMinuteData.query.filter(
                StockMinuteData.ts_code == ts_code,
                StockMinuteData.period_type == period_type,
                StockMinuteData.datetime == current_time
            ).first()
            
            if not current_data:
                return 1.0
            
            return current_data.volume / avg_volume
            
        except Exception as e:
            logger.error(f"计算 {ts_code} 成交量比失败: {str(e)}")
            return 1.0
    
    def _calculate_turnover_rate(self, ts_code: str, volume: float) -> float:
        """计算换手率（简化版本）"""
        try:
            # 这里应该根据股票的流通股本计算，简化处理返回一个估算值
            # 实际应用中需要获取股票的流通股本数据
            return min(20.0, volume / 1000000 * 0.1)  # 简化计算
            
        except Exception as e:
            logger.error(f"计算 {ts_code} 换手率失败: {str(e)}")
            return 0.0
    
    def _get_stock_name(self, ts_code: str) -> str:
        """获取股票名称"""
        try:
            stock_basic = StockBasic.query.filter_by(ts_code=ts_code).first()
            return stock_basic.name if stock_basic else ts_code
        except Exception as e:
            logger.error(f"获取 {ts_code} 股票名称失败: {str(e)}")
            return ts_code
    
    def _check_price_breakout(self, ts_code: str, latest_data) -> bool:
        """检查价格突破（简化版本）"""
        try:
            # 获取最近20个周期的最高价和最低价
            start_time = latest_data.datetime - timedelta(hours=20)
            
            price_data = StockMinuteData.query.filter(
                StockMinuteData.ts_code == ts_code,
                StockMinuteData.datetime >= start_time,
                StockMinuteData.datetime < latest_data.datetime
            ).with_entities(
                func.max(StockMinuteData.high).label('max_high'),
                func.min(StockMinuteData.low).label('min_low')
            ).first()
            
            if not price_data or not price_data.max_high or not price_data.min_low:
                return False
            
            # 检查是否突破最高价或最低价
            return (latest_data.high > price_data.max_high * 1.01 or 
                   latest_data.low < price_data.min_low * 0.99)
            
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