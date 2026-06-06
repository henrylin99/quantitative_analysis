"""
WebSocket推送服务
提供定时数据推送和事件触发推送功能
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import pandas as pd

from app.extensions import db
from app.models.realtime_indicator import RealtimeIndicator
from app.models.trading_signal import TradingSignal
from app.models.risk_alert import RiskAlert
from app.services.realtime_risk_manager import _portfolio_repo
from app.services.realtime_data_manager import RealtimeDataManager
from app.services.realtime_indicator_engine import RealtimeIndicatorEngine
from app.services.realtime_trading_signal_engine import RealtimeTradingSignalEngine
from app.services.realtime_monitor_service import RealtimeMonitorService
from app.services.realtime_risk_manager import RealtimeRiskManager
from app.services.parquet_event_store import ParquetEventStore
from app.websocket.websocket_events import (
    broadcast_market_data, broadcast_indicators, broadcast_signals,
    broadcast_monitor_data, broadcast_risk_alert, broadcast_portfolio_update,
    broadcast_news, get_connection_stats
)

logger = logging.getLogger(__name__)


class WebSocketPushService:
    """WebSocket推送服务"""
    
    def __init__(self):
        """初始化推送服务"""
        self.data_manager = RealtimeDataManager()
        self.indicator_engine = RealtimeIndicatorEngine()
        self.signal_engine = RealtimeTradingSignalEngine()
        self.monitor_service = RealtimeMonitorService()
        self.risk_manager = RealtimeRiskManager()
        self.event_store = ParquetEventStore()
        
        self.is_running = False
        self.push_interval = 30  # 推送间隔（秒）
        
        # 推送配置
        self.push_config = {
            'market_data': {'enabled': True, 'interval': 30},
            'indicators': {'enabled': True, 'interval': 60},
            'signals': {'enabled': True, 'interval': 60},
            'monitor': {'enabled': True, 'interval': 30},
            'risk_alerts': {'enabled': True, 'interval': 60},
            'portfolio': {'enabled': True, 'interval': 120},
            'news': {'enabled': False, 'interval': 300}
        }
        
        # 缓存上次推送时间
        self.last_push_times = {}
    
    def start_push_service(self):
        """启动推送服务"""
        if self.is_running:
            logger.warning("推送服务已在运行")
            return

        self.is_running = True
        from app.extensions import socketio
        socketio.start_background_task(target=self._push_loop)
        logger.info("WebSocket推送服务已启动")

    def stop_push_service(self):
        """停止推送服务"""
        self.is_running = False
        logger.info("WebSocket推送服务已停止")
    
    def _push_loop(self):
        """推送循环"""
        from app.extensions import socketio as _sio
        while self.is_running:
            try:
                current_time = datetime.now()

                # 检查各类数据是否需要推送
                for data_type, config in self.push_config.items():
                    if not config['enabled']:
                        continue

                    last_push = self.last_push_times.get(data_type)
                    if (not last_push or
                        (current_time - last_push).total_seconds() >= config['interval']):

                        self._push_data_type(data_type)
                        self.last_push_times[data_type] = current_time

                # 等待下一次检查
                _sio.sleep(10)  # 使用 socketio.sleep 保证 eventlet 兼容

            except Exception as e:
                logger.error(f"推送循环错误: {e}")
                _sio.sleep(30)
    
    def _push_data_type(self, data_type: str):
        """推送指定类型的数据"""
        try:
            if data_type == 'market_data':
                self._push_market_data()
            elif data_type == 'indicators':
                self._push_indicators()
            elif data_type == 'signals':
                self._push_signals()
            elif data_type == 'monitor':
                self._push_monitor_data()
            elif data_type == 'risk_alerts':
                self._push_risk_alerts()
            elif data_type == 'portfolio':
                self._push_portfolio_updates()
            elif data_type == 'news':
                self._push_news()
                
        except Exception as e:
            logger.error(f"推送{data_type}数据失败: {e}")
    
    def _push_market_data(self):
        """推送市场数据"""
        try:
            # 获取有分钟数据的股票列表
            active_stocks = self.data_manager.get_available_minute_stocks()

            pushed_count = 0
            for ts_code in active_stocks[:20]:  # 限制推送数量
                # 尝试各周期，优先1min，fallback到更粗粒度
                latest_data = pd.DataFrame()
                for period in ['1min', '5min', '15min', '30min', '60min']:
                    latest_data = self.data_manager.get_minute_latest_data(ts_code, period, 2)
                    if not latest_data.empty:
                        break

                if latest_data.empty:
                    continue

                row = latest_data.iloc[0]
                market_data = {
                    'ts_code': ts_code,
                    'datetime': str(row.get('datetime', '')),
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': float(row.get('volume', 0)),
                    'amount': float(row.get('amount', 0)),
                    'change_pct': self._calculate_change_pct(latest_data)
                }

                broadcast_market_data(ts_code, market_data)
                broadcast_market_data('all', market_data)  # 广播到全局房间
                pushed_count += 1

            logger.info(f"推送市场数据完成，股票数量: {pushed_count}/{len(active_stocks)}")

        except Exception as e:
            logger.error(f"推送市场数据失败: {e}")
    
    def _push_indicators(self):
        """推送技术指标数据"""
        try:
            # 获取最新指标数据
            latest_indicators = self.event_store.get_latest_indicators(
                ts_code=None,
                period_type=None,
                indicator_names=None,
                limit=50,
            )
            
            # 按股票分组
            indicators_by_stock = {}
            for _, indicator in latest_indicators.iterrows():
                ts_code = indicator.get('ts_code')
                if ts_code not in indicators_by_stock:
                    indicators_by_stock[ts_code] = []
                
                indicators_by_stock[ts_code].append({
                    'indicator_name': indicator.get('indicator_name'),
                    'period_type': indicator.get('period_type'),
                    'value1': indicator.get('value1'),
                    'value2': indicator.get('value2'),
                    'value3': indicator.get('value3'),
                    'value4': indicator.get('value4'),
                    'datetime': indicator.get('datetime').isoformat() if hasattr(indicator.get('datetime'), 'isoformat') else indicator.get('datetime')
                })
            
            # 推送指标数据
            for ts_code, indicators in indicators_by_stock.items():
                broadcast_indicators(ts_code, indicators)
                broadcast_indicators('all', {
                    'ts_code': ts_code,
                    'indicators': indicators
                })
            
            logger.debug(f"推送技术指标数据完成，股票数量: {len(indicators_by_stock)}")
            
        except Exception as e:
            logger.error(f"推送技术指标数据失败: {e}")
    
    def _push_signals(self):
        """推送交易信号"""
        try:
            # 获取最新信号
            latest_signals = self.event_store.get_recent_signals(
                since=datetime.now() - timedelta(minutes=10),
                limit=20,
                status='ACTIVE',
            )
            
            # 按股票分组
            signals_by_stock = {}
            for _, signal in latest_signals.iterrows():
                ts_code = signal.get('ts_code')
                if ts_code not in signals_by_stock:
                    signals_by_stock[ts_code] = []
                
                signals_by_stock[ts_code].append({
                    'strategy_name': signal.get('strategy_name'),
                    'signal_type': signal.get('signal_type'),
                    'signal_strength': signal.get('signal_strength'),
                    'confidence': signal.get('confidence'),
                    'created_at': signal.get('datetime').isoformat() if hasattr(signal.get('datetime'), 'isoformat') else signal.get('datetime'),
                    'parameters': signal.get('strategy_params')
                })
            
            # 推送信号数据
            for ts_code, signals in signals_by_stock.items():
                broadcast_signals(ts_code, signals)
                broadcast_signals('all', {
                    'ts_code': ts_code,
                    'signals': signals
                })
            
            logger.debug(f"推送交易信号完成，股票数量: {len(signals_by_stock)}")
            
        except Exception as e:
            logger.error(f"推送交易信号失败: {e}")
    
    def _push_monitor_data(self):
        """推送监控数据"""
        try:
            # 获取监控数据
            anomaly_result = self.monitor_service.detect_anomalies(
                change_threshold=5.0, volume_threshold=3.0
            )
            anomaly_list = anomaly_result.get('data', {}).get('anomalies', []) \
                if isinstance(anomaly_result, dict) and anomaly_result.get('success') else []

            monitor_data = {
                'market_overview': self.data_manager.get_market_overview(),
                'top_movers': anomaly_list,
                'anomalies': anomaly_list,
                'sentiment': self.monitor_service.get_market_sentiment(period_hours=1)
            }

            broadcast_monitor_data(monitor_data)
            logger.info("推送监控数据完成")

        except Exception as e:
            logger.error(f"推送监控数据失败: {e}")
    
    def _push_risk_alerts(self):
        """推送风险预警"""
        try:
            # 获取最新风险预警
            latest_alerts = RiskAlert.get_recent_alerts(minutes=10, active_only=True, limit=10)
            
            for alert in latest_alerts:
                alert_data = {
                    'id': alert.id,
                    'portfolio_id': alert.portfolio_id,
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                    'message': alert.message,
                    'threshold_value': alert.threshold_value,
                    'current_value': alert.current_value,
                    'created_at': alert.created_at.isoformat()
                }
                
                broadcast_risk_alert(alert_data)
            
            logger.debug(f"推送风险预警完成，预警数量: {len(latest_alerts)}")
            
        except Exception as e:
            logger.error(f"推送风险预警失败: {e}")
    
    def _push_portfolio_updates(self):
        """推送投资组合更新"""
        try:
            portfolio_ids = self._get_active_portfolio_ids()
            if not portfolio_ids:
                logger.debug("未找到真实投资组合，跳过组合推送")
                return
            
            for portfolio_id in portfolio_ids:
                # 获取投资组合指标
                portfolio_metrics = self.risk_manager.calculate_portfolio_risk(portfolio_id)
                
                portfolio_data = {
                    'portfolio_id': portfolio_id,
                    'metrics': portfolio_metrics,
                    'updated_at': datetime.now().isoformat()
                }
                
                broadcast_portfolio_update(portfolio_id, portfolio_data)
            
            logger.debug(f"推送投资组合更新完成，组合数量: {len(portfolio_ids)}")
            
        except Exception as e:
            logger.error(f"推送投资组合更新失败: {e}")

    def _get_active_portfolio_ids(self) -> List[str]:
        """获取存在真实持仓的活跃投资组合ID。"""
        try:
            return _portfolio_repo.list_portfolio_ids(active_only=True)
        except Exception as e:
            logger.error(f"获取活跃投资组合失败: {e}")
            return []
    
    def _push_news(self):
        """推送新闻资讯"""
        try:
            news_data = self._get_news_payload()
            if not news_data:
                logger.debug("未配置真实新闻源，跳过新闻推送")
                return

            broadcast_news(news_data)
            logger.debug("推送新闻资讯完成")
            
        except Exception as e:
            logger.error(f"推送新闻资讯失败: {e}")

    def _get_news_payload(self) -> List[Dict[str, Any]]:
        """获取可推送的新闻数据。默认不生成模拟新闻。"""
        return []
    
    def _calculate_change_pct(self, latest_data) -> float:
        """计算涨跌幅，传入最近2条DataFrame记录"""
        try:
            if latest_data.empty:
                return 0.0
            current_close = float(latest_data.iloc[0].get('close', 0))
            if len(latest_data) >= 2:
                prev_close = float(latest_data.iloc[1].get('close', 0))
            else:
                # 只有1条数据时用开盘价作为近似
                prev_close = float(latest_data.iloc[0].get('open', current_close))

            if prev_close and prev_close != 0:
                return round(((current_close - prev_close) / prev_close) * 100, 2)
            return 0.0

        except Exception:
            return 0.0
    
    def trigger_immediate_push(self, data_type: str, data: Any):
        """触发立即推送"""
        try:
            if data_type == 'market_data':
                symbol = data.get('ts_code', 'unknown')
                broadcast_market_data(symbol, data)
                broadcast_market_data('all', data)
                
            elif data_type == 'signal':
                symbol = data.get('ts_code', 'unknown')
                broadcast_signals(symbol, [data])
                broadcast_signals('all', {'ts_code': symbol, 'signals': [data]})
                
            elif data_type == 'risk_alert':
                broadcast_risk_alert(data)
                
            elif data_type == 'monitor':
                broadcast_monitor_data(data)
                
            logger.debug(f"立即推送{data_type}数据完成")
            
        except Exception as e:
            logger.error(f"立即推送{data_type}数据失败: {e}")
    
    def update_push_config(self, config: Dict[str, Any]):
        """更新推送配置"""
        try:
            for data_type, settings in config.items():
                if data_type in self.push_config:
                    self.push_config[data_type].update(settings)
            
            logger.info(f"推送配置已更新: {config}")
            
        except Exception as e:
            logger.error(f"更新推送配置失败: {e}")
    
    def get_push_status(self) -> Dict[str, Any]:
        """获取推送状态"""
        return {
            'is_running': self.is_running,
            'push_interval': self.push_interval,
            'push_config': self.push_config,
            'last_push_times': {
                k: v.isoformat() if v else None 
                for k, v in self.last_push_times.items()
            },
            'connection_stats': get_connection_stats()
        }


# 全局推送服务实例
push_service = WebSocketPushService() 
