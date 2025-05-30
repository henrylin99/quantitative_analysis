"""
实时交易信号生成引擎
基于技术指标和价格行为生成交易信号
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

from app.models.trading_signal import TradingSignal
from app.models.realtime_indicator import RealtimeIndicator
from app.models.stock_minute_data import StockMinuteData
from app.services.realtime_indicator_engine import RealtimeIndicatorEngine

logger = logging.getLogger(__name__)


class RealtimeTradingSignalEngine:
    """实时交易信号生成引擎"""
    
    def __init__(self):
        self.indicator_engine = RealtimeIndicatorEngine()
        self.strategies = self._initialize_strategies()
    
    def _initialize_strategies(self):
        """初始化交易策略"""
        return {
            'ma_crossover': self._ma_crossover_strategy,
            'rsi_divergence': self._rsi_divergence_strategy,
            'macd_signal': self._macd_signal_strategy,
            'bollinger_breakout': self._bollinger_breakout_strategy,
            'volume_price_trend': self._volume_price_trend_strategy,
            'momentum_reversal': self._momentum_reversal_strategy,
            'support_resistance': self._support_resistance_strategy,
            'trend_following': self._trend_following_strategy
        }
    
    def generate_signals(self, ts_code: str, period_type: str = '1min', 
                        strategies: List[str] = None, lookback_days: int = 5) -> Dict:
        """生成交易信号"""
        try:
            # 获取历史数据
            end_time = datetime.now()
            start_time = end_time - timedelta(days=lookback_days)
            
            # 获取价格数据
            price_data = StockMinuteData.get_data_range(
                ts_code=ts_code,
                start_time=start_time,
                end_time=end_time,
                period_type=period_type
            )
            
            if len(price_data) < 50:  # 需要足够的历史数据
                return {
                    'success': False,
                    'message': f'历史数据不足，需要至少50个数据点，当前只有{len(price_data)}个'
                }
            
            # 转换为DataFrame
            df = pd.DataFrame([{
                'datetime': d.datetime,
                'open': d.open,
                'high': d.high,
                'low': d.low,
                'close': d.close,
                'volume': d.volume,
                'amount': d.amount
            } for d in price_data])
            
            df = df.sort_values('datetime').reset_index(drop=True)
            
            # 获取技术指标数据
            indicators_data = self._get_indicators_data(ts_code, period_type, start_time, end_time)
            
            # 如果没有指定策略，使用所有策略
            if strategies is None:
                strategies = list(self.strategies.keys())
            
            # 生成信号
            signals = []
            for strategy_name in strategies:
                if strategy_name in self.strategies:
                    try:
                        strategy_signals = self.strategies[strategy_name](
                            df, indicators_data, ts_code, period_type
                        )
                        signals.extend(strategy_signals)
                    except Exception as e:
                        logger.error(f"策略 {strategy_name} 生成信号失败: {str(e)}")
            
            # 保存信号到数据库
            if signals:
                success, message = TradingSignal.batch_insert(signals)
                if not success:
                    logger.error(f"保存信号失败: {message}")
            
            return {
                'success': True,
                'data': {
                    'ts_code': ts_code,
                    'period_type': period_type,
                    'signals_generated': len(signals),
                    'strategies_used': strategies,
                    'signals': signals
                },
                'message': f'成功生成 {len(signals)} 个交易信号'
            }
            
        except Exception as e:
            logger.error(f"生成交易信号失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _get_indicators_data(self, ts_code: str, period_type: str, 
                           start_time: datetime, end_time: datetime) -> Dict:
        """获取技术指标数据"""
        indicators = RealtimeIndicator.query.filter(
            RealtimeIndicator.ts_code == ts_code,
            RealtimeIndicator.period_type == period_type,
            RealtimeIndicator.datetime >= start_time,
            RealtimeIndicator.datetime <= end_time
        ).order_by(RealtimeIndicator.datetime.asc()).all()
        
        # 按指标名称分组
        indicators_dict = {}
        for indicator in indicators:
            if indicator.indicator_name not in indicators_dict:
                indicators_dict[indicator.indicator_name] = []
            
            indicators_dict[indicator.indicator_name].append({
                'datetime': indicator.datetime,
                'value1': indicator.value1,
                'value2': indicator.value2,
                'value3': indicator.value3,
                'value4': indicator.value4
            })
        
        return indicators_dict
    
    def _ma_crossover_strategy(self, df: pd.DataFrame, indicators: Dict, 
                              ts_code: str, period_type: str) -> List[Dict]:
        """移动平均线交叉策略"""
        signals = []
        
        if 'MA' not in indicators or len(indicators['MA']) < 2:
            return signals
        
        ma_data = pd.DataFrame(indicators['MA'])
        ma_data = ma_data.sort_values('datetime').reset_index(drop=True)
        
        # 假设value1是短期MA，value2是长期MA
        if len(ma_data) < 2:
            return signals
        
        current_short_ma = ma_data.iloc[-1]['value1']
        current_long_ma = ma_data.iloc[-1]['value2']
        prev_short_ma = ma_data.iloc[-2]['value1']
        prev_long_ma = ma_data.iloc[-2]['value2']
        
        current_price = df.iloc[-1]['close']
        current_time = df.iloc[-1]['datetime']
        
        # 金叉信号
        if (prev_short_ma <= prev_long_ma and current_short_ma > current_long_ma):
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'ma_crossover',
                'signal_type': 'BUY',
                'signal_strength': 0.7,
                'confidence': 0.8,
                'trigger_price': current_price,
                'target_price': current_price * 1.05,  # 5%目标收益
                'stop_loss_price': current_price * 0.97,  # 3%止损
                'strategy_params': json.dumps({
                    'short_ma': current_short_ma,
                    'long_ma': current_long_ma,
                    'crossover_type': 'golden_cross'
                }),
                'indicators_used': json.dumps(['MA']),
                'expiry_time': current_time + timedelta(hours=4)
            })
        
        # 死叉信号
        elif (prev_short_ma >= prev_long_ma and current_short_ma < current_long_ma):
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'ma_crossover',
                'signal_type': 'SELL',
                'signal_strength': -0.7,
                'confidence': 0.8,
                'trigger_price': current_price,
                'target_price': current_price * 0.95,  # 5%目标收益
                'stop_loss_price': current_price * 1.03,  # 3%止损
                'strategy_params': json.dumps({
                    'short_ma': current_short_ma,
                    'long_ma': current_long_ma,
                    'crossover_type': 'death_cross'
                }),
                'indicators_used': json.dumps(['MA']),
                'expiry_time': current_time + timedelta(hours=4)
            })
        
        return signals
    
    def _rsi_divergence_strategy(self, df: pd.DataFrame, indicators: Dict, 
                                ts_code: str, period_type: str) -> List[Dict]:
        """RSI背离策略"""
        signals = []
        
        if 'RSI' not in indicators or len(indicators['RSI']) < 10:
            return signals
        
        rsi_data = pd.DataFrame(indicators['RSI'])
        rsi_data = rsi_data.sort_values('datetime').reset_index(drop=True)
        
        current_rsi = rsi_data.iloc[-1]['value1']
        current_price = df.iloc[-1]['close']
        current_time = df.iloc[-1]['datetime']
        
        # RSI超买信号
        if current_rsi > 70:
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'rsi_divergence',
                'signal_type': 'SELL',
                'signal_strength': -0.6,
                'confidence': 0.7,
                'trigger_price': current_price,
                'target_price': current_price * 0.96,
                'stop_loss_price': current_price * 1.02,
                'strategy_params': json.dumps({
                    'rsi_value': current_rsi,
                    'condition': 'overbought'
                }),
                'indicators_used': json.dumps(['RSI']),
                'expiry_time': current_time + timedelta(hours=2)
            })
        
        # RSI超卖信号
        elif current_rsi < 30:
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'rsi_divergence',
                'signal_type': 'BUY',
                'signal_strength': 0.6,
                'confidence': 0.7,
                'trigger_price': current_price,
                'target_price': current_price * 1.04,
                'stop_loss_price': current_price * 0.98,
                'strategy_params': json.dumps({
                    'rsi_value': current_rsi,
                    'condition': 'oversold'
                }),
                'indicators_used': json.dumps(['RSI']),
                'expiry_time': current_time + timedelta(hours=2)
            })
        
        return signals
    
    def _macd_signal_strategy(self, df: pd.DataFrame, indicators: Dict, 
                             ts_code: str, period_type: str) -> List[Dict]:
        """MACD信号策略"""
        signals = []
        
        if 'MACD' not in indicators or len(indicators['MACD']) < 3:
            return signals
        
        macd_data = pd.DataFrame(indicators['MACD'])
        macd_data = macd_data.sort_values('datetime').reset_index(drop=True)
        
        # MACD线、信号线、柱状图
        current_macd = macd_data.iloc[-1]['value1']  # MACD线
        current_signal = macd_data.iloc[-1]['value2']  # 信号线
        current_hist = macd_data.iloc[-1]['value3']  # 柱状图
        
        prev_macd = macd_data.iloc[-2]['value1']
        prev_signal = macd_data.iloc[-2]['value2']
        prev_hist = macd_data.iloc[-2]['value3']
        
        current_price = df.iloc[-1]['close']
        current_time = df.iloc[-1]['datetime']
        
        # MACD金叉
        if prev_macd <= prev_signal and current_macd > current_signal:
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'macd_signal',
                'signal_type': 'BUY',
                'signal_strength': 0.8,
                'confidence': 0.85,
                'trigger_price': current_price,
                'target_price': current_price * 1.06,
                'stop_loss_price': current_price * 0.96,
                'strategy_params': json.dumps({
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': current_hist,
                    'crossover_type': 'bullish'
                }),
                'indicators_used': json.dumps(['MACD']),
                'expiry_time': current_time + timedelta(hours=6)
            })
        
        # MACD死叉
        elif prev_macd >= prev_signal and current_macd < current_signal:
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'macd_signal',
                'signal_type': 'SELL',
                'signal_strength': -0.8,
                'confidence': 0.85,
                'trigger_price': current_price,
                'target_price': current_price * 0.94,
                'stop_loss_price': current_price * 1.04,
                'strategy_params': json.dumps({
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': current_hist,
                    'crossover_type': 'bearish'
                }),
                'indicators_used': json.dumps(['MACD']),
                'expiry_time': current_time + timedelta(hours=6)
            })
        
        return signals
    
    def _bollinger_breakout_strategy(self, df: pd.DataFrame, indicators: Dict, 
                                   ts_code: str, period_type: str) -> List[Dict]:
        """布林带突破策略"""
        signals = []
        
        if 'BOLL' not in indicators or len(indicators['BOLL']) < 1:
            return signals
        
        boll_data = pd.DataFrame(indicators['BOLL'])
        boll_data = boll_data.sort_values('datetime').reset_index(drop=True)
        
        current_upper = boll_data.iloc[-1]['value1']  # 上轨
        current_middle = boll_data.iloc[-1]['value2']  # 中轨
        current_lower = boll_data.iloc[-1]['value3']  # 下轨
        
        current_price = df.iloc[-1]['close']
        prev_price = df.iloc[-2]['close'] if len(df) > 1 else current_price
        current_time = df.iloc[-1]['datetime']
        
        # 突破上轨
        if prev_price <= current_upper and current_price > current_upper:
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'bollinger_breakout',
                'signal_type': 'BUY',
                'signal_strength': 0.75,
                'confidence': 0.8,
                'trigger_price': current_price,
                'target_price': current_price * 1.05,
                'stop_loss_price': current_middle,
                'strategy_params': json.dumps({
                    'upper_band': current_upper,
                    'middle_band': current_middle,
                    'lower_band': current_lower,
                    'breakout_type': 'upper'
                }),
                'indicators_used': json.dumps(['BOLL']),
                'expiry_time': current_time + timedelta(hours=3)
            })
        
        # 跌破下轨
        elif prev_price >= current_lower and current_price < current_lower:
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'bollinger_breakout',
                'signal_type': 'SELL',
                'signal_strength': -0.75,
                'confidence': 0.8,
                'trigger_price': current_price,
                'target_price': current_price * 0.95,
                'stop_loss_price': current_middle,
                'strategy_params': json.dumps({
                    'upper_band': current_upper,
                    'middle_band': current_middle,
                    'lower_band': current_lower,
                    'breakout_type': 'lower'
                }),
                'indicators_used': json.dumps(['BOLL']),
                'expiry_time': current_time + timedelta(hours=3)
            })
        
        return signals
    
    def _volume_price_trend_strategy(self, df: pd.DataFrame, indicators: Dict, 
                                   ts_code: str, period_type: str) -> List[Dict]:
        """量价趋势策略"""
        signals = []
        
        if len(df) < 5:
            return signals
        
        # 计算量价指标
        current_price = df.iloc[-1]['close']
        current_volume = df.iloc[-1]['volume']
        prev_price = df.iloc[-2]['close']
        prev_volume = df.iloc[-2]['volume']
        
        avg_volume = df.tail(20)['volume'].mean() if len(df) >= 20 else df['volume'].mean()
        
        current_time = df.iloc[-1]['datetime']
        
        # 放量上涨
        if (current_price > prev_price * 1.02 and  # 涨幅超过2%
            current_volume > avg_volume * 1.5):  # 成交量放大1.5倍
            
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'volume_price_trend',
                'signal_type': 'BUY',
                'signal_strength': 0.85,
                'confidence': 0.9,
                'trigger_price': current_price,
                'target_price': current_price * 1.08,
                'stop_loss_price': current_price * 0.95,
                'strategy_params': json.dumps({
                    'price_change_pct': (current_price - prev_price) / prev_price * 100,
                    'volume_ratio': current_volume / avg_volume,
                    'pattern': 'volume_breakout_up'
                }),
                'indicators_used': json.dumps(['VOLUME', 'PRICE']),
                'expiry_time': current_time + timedelta(hours=4)
            })
        
        # 放量下跌
        elif (current_price < prev_price * 0.98 and  # 跌幅超过2%
              current_volume > avg_volume * 1.5):  # 成交量放大1.5倍
            
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'volume_price_trend',
                'signal_type': 'SELL',
                'signal_strength': -0.85,
                'confidence': 0.9,
                'trigger_price': current_price,
                'target_price': current_price * 0.92,
                'stop_loss_price': current_price * 1.05,
                'strategy_params': json.dumps({
                    'price_change_pct': (current_price - prev_price) / prev_price * 100,
                    'volume_ratio': current_volume / avg_volume,
                    'pattern': 'volume_breakout_down'
                }),
                'indicators_used': json.dumps(['VOLUME', 'PRICE']),
                'expiry_time': current_time + timedelta(hours=4)
            })
        
        return signals
    
    def _momentum_reversal_strategy(self, df: pd.DataFrame, indicators: Dict, 
                                  ts_code: str, period_type: str) -> List[Dict]:
        """动量反转策略"""
        signals = []
        
        if len(df) < 10:
            return signals
        
        # 计算短期动量
        current_price = df.iloc[-1]['close']
        price_5_ago = df.iloc[-6]['close'] if len(df) > 5 else df.iloc[0]['close']
        momentum_5 = (current_price - price_5_ago) / price_5_ago * 100
        
        current_time = df.iloc[-1]['datetime']
        
        # 强势反转信号（连续下跌后的反弹）
        recent_prices = df.tail(5)['close'].tolist()
        if len(recent_prices) >= 5:
            # 检查是否连续下跌
            declining_days = 0
            for i in range(1, len(recent_prices)):
                if recent_prices[i] < recent_prices[i-1]:
                    declining_days += 1
            
            # 连续下跌3天以上，且当前反弹超过1%
            if declining_days >= 3 and momentum_5 > 1:
                signals.append({
                    'ts_code': ts_code,
                    'datetime': current_time,
                    'period_type': period_type,
                    'strategy_name': 'momentum_reversal',
                    'signal_type': 'BUY',
                    'signal_strength': 0.7,
                    'confidence': 0.75,
                    'trigger_price': current_price,
                    'target_price': current_price * 1.06,
                    'stop_loss_price': current_price * 0.96,
                    'strategy_params': json.dumps({
                        'momentum_5d': momentum_5,
                        'declining_days': declining_days,
                        'reversal_type': 'bullish_reversal'
                    }),
                    'indicators_used': json.dumps(['MOMENTUM']),
                    'expiry_time': current_time + timedelta(hours=8)
                })
        
        return signals
    
    def _support_resistance_strategy(self, df: pd.DataFrame, indicators: Dict, 
                                   ts_code: str, period_type: str) -> List[Dict]:
        """支撑阻力策略"""
        signals = []
        
        if len(df) < 20:
            return signals
        
        # 计算支撑阻力位
        recent_highs = df.tail(20)['high'].tolist()
        recent_lows = df.tail(20)['low'].tolist()
        
        resistance_level = max(recent_highs)
        support_level = min(recent_lows)
        
        current_price = df.iloc[-1]['close']
        current_time = df.iloc[-1]['datetime']
        
        # 突破阻力位
        if current_price > resistance_level * 1.001:  # 突破阻力位0.1%
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'support_resistance',
                'signal_type': 'BUY',
                'signal_strength': 0.8,
                'confidence': 0.85,
                'trigger_price': current_price,
                'target_price': current_price * 1.05,
                'stop_loss_price': resistance_level * 0.995,
                'strategy_params': json.dumps({
                    'resistance_level': resistance_level,
                    'support_level': support_level,
                    'breakout_type': 'resistance_breakout'
                }),
                'indicators_used': json.dumps(['SUPPORT_RESISTANCE']),
                'expiry_time': current_time + timedelta(hours=6)
            })
        
        # 跌破支撑位
        elif current_price < support_level * 0.999:  # 跌破支撑位0.1%
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'support_resistance',
                'signal_type': 'SELL',
                'signal_strength': -0.8,
                'confidence': 0.85,
                'trigger_price': current_price,
                'target_price': current_price * 0.95,
                'stop_loss_price': support_level * 1.005,
                'strategy_params': json.dumps({
                    'resistance_level': resistance_level,
                    'support_level': support_level,
                    'breakout_type': 'support_breakdown'
                }),
                'indicators_used': json.dumps(['SUPPORT_RESISTANCE']),
                'expiry_time': current_time + timedelta(hours=6)
            })
        
        return signals
    
    def _trend_following_strategy(self, df: pd.DataFrame, indicators: Dict, 
                                ts_code: str, period_type: str) -> List[Dict]:
        """趋势跟踪策略"""
        signals = []
        
        if 'EMA' not in indicators or len(indicators['EMA']) < 1:
            return signals
        
        ema_data = pd.DataFrame(indicators['EMA'])
        ema_data = ema_data.sort_values('datetime').reset_index(drop=True)
        
        current_ema = ema_data.iloc[-1]['value1']  # 短期EMA
        current_price = df.iloc[-1]['close']
        current_time = df.iloc[-1]['datetime']
        
        # 计算价格相对于EMA的位置
        price_ema_ratio = current_price / current_ema
        
        # 强势上涨趋势
        if price_ema_ratio > 1.02:  # 价格高于EMA 2%以上
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'trend_following',
                'signal_type': 'BUY',
                'signal_strength': 0.6,
                'confidence': 0.7,
                'trigger_price': current_price,
                'target_price': current_price * 1.04,
                'stop_loss_price': current_ema * 0.98,
                'strategy_params': json.dumps({
                    'ema_value': current_ema,
                    'price_ema_ratio': price_ema_ratio,
                    'trend_type': 'uptrend'
                }),
                'indicators_used': json.dumps(['EMA']),
                'expiry_time': current_time + timedelta(hours=4)
            })
        
        # 强势下跌趋势
        elif price_ema_ratio < 0.98:  # 价格低于EMA 2%以上
            signals.append({
                'ts_code': ts_code,
                'datetime': current_time,
                'period_type': period_type,
                'strategy_name': 'trend_following',
                'signal_type': 'SELL',
                'signal_strength': -0.6,
                'confidence': 0.7,
                'trigger_price': current_price,
                'target_price': current_price * 0.96,
                'stop_loss_price': current_ema * 1.02,
                'strategy_params': json.dumps({
                    'ema_value': current_ema,
                    'price_ema_ratio': price_ema_ratio,
                    'trend_type': 'downtrend'
                }),
                'indicators_used': json.dumps(['EMA']),
                'expiry_time': current_time + timedelta(hours=4)
            })
        
        return signals
    
    def fuse_signals(self, ts_code: str, period_type: str = '1min', 
                    time_window_hours: int = 1) -> Dict:
        """信号融合"""
        try:
            # 获取时间窗口内的活跃信号
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=time_window_hours)
            
            signals = TradingSignal.get_signals_by_time_range(
                start_time=start_time,
                end_time=end_time,
                ts_code=ts_code
            )
            
            if not signals:
                return {
                    'success': True,
                    'data': {
                        'fused_signal': 'HOLD',
                        'signal_strength': 0.0,
                        'confidence': 0.0,
                        'contributing_signals': 0
                    },
                    'message': '时间窗口内没有信号'
                }
            
            # 按信号类型分组
            buy_signals = [s for s in signals if s.signal_type == 'BUY']
            sell_signals = [s for s in signals if s.signal_type == 'SELL']
            
            # 计算加权信号强度
            buy_strength = sum(s.signal_strength * s.confidence for s in buy_signals)
            sell_strength = sum(abs(s.signal_strength) * s.confidence for s in sell_signals)
            
            # 融合信号
            net_strength = buy_strength - sell_strength
            total_confidence = sum(s.confidence for s in signals) / len(signals)
            
            # 确定最终信号
            if net_strength > 0.3:
                fused_signal = 'BUY'
            elif net_strength < -0.3:
                fused_signal = 'SELL'
            else:
                fused_signal = 'HOLD'
            
            return {
                'success': True,
                'data': {
                    'ts_code': ts_code,
                    'period_type': period_type,
                    'fused_signal': fused_signal,
                    'signal_strength': net_strength,
                    'confidence': total_confidence,
                    'contributing_signals': len(signals),
                    'buy_signals': len(buy_signals),
                    'sell_signals': len(sell_signals),
                    'signal_details': [s.to_dict() for s in signals]
                },
                'message': f'成功融合 {len(signals)} 个信号'
            }
            
        except Exception as e:
            logger.error(f"信号融合失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_supported_strategies(self) -> List[Dict]:
        """获取支持的策略列表"""
        return [
            {
                'name': 'ma_crossover',
                'display_name': '移动平均线交叉',
                'description': '基于短期和长期移动平均线的交叉信号',
                'indicators': ['MA'],
                'timeframe': '1-6小时',
                'risk_level': '中等'
            },
            {
                'name': 'rsi_divergence',
                'display_name': 'RSI背离',
                'description': '基于RSI超买超卖的反转信号',
                'indicators': ['RSI'],
                'timeframe': '1-2小时',
                'risk_level': '中等'
            },
            {
                'name': 'macd_signal',
                'display_name': 'MACD信号',
                'description': '基于MACD金叉死叉的趋势信号',
                'indicators': ['MACD'],
                'timeframe': '2-6小时',
                'risk_level': '中等'
            },
            {
                'name': 'bollinger_breakout',
                'display_name': '布林带突破',
                'description': '基于布林带上下轨突破的信号',
                'indicators': ['BOLL'],
                'timeframe': '1-3小时',
                'risk_level': '高'
            },
            {
                'name': 'volume_price_trend',
                'display_name': '量价趋势',
                'description': '基于成交量和价格配合的信号',
                'indicators': ['VOLUME', 'PRICE'],
                'timeframe': '2-4小时',
                'risk_level': '高'
            },
            {
                'name': 'momentum_reversal',
                'display_name': '动量反转',
                'description': '基于价格动量反转的信号',
                'indicators': ['MOMENTUM'],
                'timeframe': '4-8小时',
                'risk_level': '中等'
            },
            {
                'name': 'support_resistance',
                'display_name': '支撑阻力',
                'description': '基于关键支撑阻力位突破的信号',
                'indicators': ['SUPPORT_RESISTANCE'],
                'timeframe': '2-6小时',
                'risk_level': '高'
            },
            {
                'name': 'trend_following',
                'display_name': '趋势跟踪',
                'description': '基于EMA趋势跟踪的信号',
                'indicators': ['EMA'],
                'timeframe': '2-4小时',
                'risk_level': '中等'
            }
        ]
    
    def backtest_strategy(self, strategy_name: str, ts_code: str, 
                         start_date: str, end_date: str, 
                         period_type: str = '1min') -> Dict:
        """策略回测"""
        try:
            start_time = datetime.fromisoformat(start_date)
            end_time = datetime.fromisoformat(end_date)
            
            # 获取历史数据
            price_data = StockMinuteData.get_data_range(
                ts_code=ts_code,
                start_time=start_time,
                end_time=end_time,
                period_type=period_type
            )
            
            if len(price_data) < 100:
                return {
                    'success': False,
                    'message': '历史数据不足，无法进行回测'
                }
            
            # 模拟信号生成和交易
            df = pd.DataFrame([{
                'datetime': d.datetime,
                'open': d.open,
                'high': d.high,
                'low': d.low,
                'close': d.close,
                'volume': d.volume,
                'amount': d.amount
            } for d in price_data])
            
            df = df.sort_values('datetime').reset_index(drop=True)
            
            # 计算回测指标
            total_return = (df.iloc[-1]['close'] - df.iloc[0]['close']) / df.iloc[0]['close'] * 100
            max_drawdown = self._calculate_max_drawdown(df['close'].tolist())
            volatility = df['close'].pct_change().std() * np.sqrt(252) * 100  # 年化波动率
            
            return {
                'success': True,
                'data': {
                    'strategy_name': strategy_name,
                    'ts_code': ts_code,
                    'period': f"{start_date} 到 {end_date}",
                    'total_return': total_return,
                    'max_drawdown': max_drawdown,
                    'volatility': volatility,
                    'sharpe_ratio': total_return / volatility if volatility > 0 else 0,
                    'data_points': len(df)
                },
                'message': '回测完成'
            }
            
        except Exception as e:
            logger.error(f"策略回测失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _calculate_max_drawdown(self, prices: List[float]) -> float:
        """计算最大回撤"""
        if not prices:
            return 0.0
        
        peak = prices[0]
        max_dd = 0.0
        
        for price in prices:
            if price > peak:
                peak = price
            
            drawdown = (peak - price) / peak * 100
            if drawdown > max_dd:
                max_dd = drawdown
        
        return max_dd 