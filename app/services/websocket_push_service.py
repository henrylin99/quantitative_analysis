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

from app.extensions import db
from app.models.stock_minute_data import StockMinuteData
from app.models.realtime_indicator import RealtimeIndicator
from app.models.trading_signal import TradingSignal
from app.models.risk_alert import RiskAlert
from app.services.realtime_data_manager import RealtimeDataManager
from app.services.realtime_indicator_engine import RealtimeIndicatorEngine
from app.services.realtime_trading_signal_engine import RealtimeTradingSignalEngine
from app.services.realtime_monitor_service import RealtimeMonitorService
from app.services.realtime_risk_manager import RealtimeRiskManager
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
        
        self.is_running = False
        self.push_thread = None
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
        self.push_thread = threading.Thread(target=self._push_loop, daemon=True)
        self.push_thread.start()
        logger.info("WebSocket推送服务已启动")
    
    def stop_push_service(self):
        """停止推送服务"""
        self.is_running = False
        if self.push_thread:
            self.push_thread.join(timeout=5)
        logger.info("WebSocket推送服务已停止")
    
    def _push_loop(self):
        """推送循环"""
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
                time.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                logger.error(f"推送循环错误: {e}")
                time.sleep(30)  # 出错后等待30秒再继续
    
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
            # 获取活跃股票列表
            active_stocks = self.data_manager.get_active_stocks()
            
            for stock in active_stocks[:20]:  # 限制推送数量
                ts_code = stock['ts_code']
                
                # 获取最新数据
                latest_data = self.data_manager.get_latest_data(ts_code, '1min', 1)
                if latest_data:
                    market_data = {
                        'ts_code': ts_code,
                        'datetime': latest_data[0]['datetime'],
                        'open': latest_data[0]['open'],
                        'high': latest_data[0]['high'],
                        'low': latest_data[0]['low'],
                        'close': latest_data[0]['close'],
                        'volume': latest_data[0]['volume'],
                        'amount': latest_data[0]['amount'],
                        'change_pct': self._calculate_change_pct(latest_data[0])
                    }
                    
                    broadcast_market_data(ts_code, market_data)
                    broadcast_market_data('all', market_data)  # 广播到全局房间
            
            logger.debug(f"推送市场数据完成，股票数量: {len(active_stocks)}")
            
        except Exception as e:
            logger.error(f"推送市场数据失败: {e}")
    
    def _push_indicators(self):
        """推送技术指标数据"""
        try:
            # 获取最新指标数据
            latest_indicators = RealtimeIndicator.query.filter(
                RealtimeIndicator.datetime >= datetime.now() - timedelta(minutes=5)
            ).limit(50).all()
            
            # 按股票分组
            indicators_by_stock = {}
            for indicator in latest_indicators:
                ts_code = indicator.ts_code
                if ts_code not in indicators_by_stock:
                    indicators_by_stock[ts_code] = []
                
                indicators_by_stock[ts_code].append({
                    'indicator_name': indicator.indicator_name,
                    'period_type': indicator.period_type,
                    'value': indicator.value,
                    'datetime': indicator.datetime.isoformat()
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
            latest_signals = TradingSignal.query.filter(
                TradingSignal.created_at >= datetime.now() - timedelta(minutes=10),
                TradingSignal.status == 'active'
            ).limit(20).all()
            
            # 按股票分组
            signals_by_stock = {}
            for signal in latest_signals:
                ts_code = signal.ts_code
                if ts_code not in signals_by_stock:
                    signals_by_stock[ts_code] = []
                
                signals_by_stock[ts_code].append({
                    'strategy_name': signal.strategy_name,
                    'signal_type': signal.signal_type,
                    'signal_strength': signal.signal_strength,
                    'confidence': signal.confidence,
                    'created_at': signal.created_at.isoformat(),
                    'parameters': signal.parameters
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
            monitor_data = {
                'market_overview': self.monitor_service.get_market_overview(),
                'top_movers': self.monitor_service.get_top_movers(limit=10),
                'anomalies': self.monitor_service.detect_anomalies(
                    change_threshold=5.0, volume_threshold=3.0
                ),
                'sentiment': self.monitor_service.calculate_market_sentiment(period_hours=1)
            }
            
            broadcast_monitor_data(monitor_data)
            logger.debug("推送监控数据完成")
            
        except Exception as e:
            logger.error(f"推送监控数据失败: {e}")
    
    def _push_risk_alerts(self):
        """推送风险预警"""
        try:
            # 获取最新风险预警
            latest_alerts = RiskAlert.query.filter(
                RiskAlert.created_at >= datetime.now() - timedelta(minutes=10),
                RiskAlert.status == 'active'
            ).limit(10).all()
            
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
            # 获取活跃投资组合
            portfolio_ids = ['demo_portfolio']  # 可以从数据库获取
            
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
    
    def _push_news(self):
        """推送新闻资讯"""
        try:
            # 模拟新闻数据（实际应用中可以对接新闻API）
            news_data = [
                {
                    'id': f'news_{int(time.time())}',
                    'title': '市场动态更新',
                    'content': '实时市场数据推送正常运行',
                    'source': '系统通知',
                    'published_at': datetime.now().isoformat(),
                    'category': 'system'
                }
            ]
            
            broadcast_news(news_data)
            logger.debug("推送新闻资讯完成")
            
        except Exception as e:
            logger.error(f"推送新闻资讯失败: {e}")
    
    def _calculate_change_pct(self, current_data: Dict) -> float:
        """计算涨跌幅"""
        try:
            # 获取前一个交易日收盘价（简化处理）
            prev_close = current_data.get('open', current_data['close'])
            current_close = current_data['close']
            
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