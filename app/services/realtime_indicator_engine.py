"""
实时技术指标计算引擎
支持常用技术指标的实时计算和存储
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from app.extensions import db
from loguru import logger
import json
import math

from app.models.stock_minute_data import StockMinuteData
from app.models.realtime_indicator import RealtimeIndicator

logger = logger.bind(name=__name__)


class RealtimeIndicatorEngine:
    """实时技术指标计算引擎"""
    
    def __init__(self):
        """初始化指标引擎"""
        self.supported_indicators = {
            'MA': self._calculate_ma,
            'EMA': self._calculate_ema,
            'MACD': self._calculate_macd,
            'RSI': self._calculate_rsi,
            'KDJ': self._calculate_kdj,
            'BOLL': self._calculate_boll,
            'CCI': self._calculate_cci,
            'WR': self._calculate_wr,
            'ATR': self._calculate_atr,
            'OBV': self._calculate_obv
        }
        
        # 默认参数配置
        self.default_params = {
            'MA': {'periods': [5, 10, 20, 30, 60]},
            'EMA': {'periods': [12, 26]},
            'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
            'RSI': {'period': 14},
            'KDJ': {'k_period': 9, 'd_period': 3, 'j_period': 3},
            'BOLL': {'period': 20, 'std_dev': 2},
            'CCI': {'period': 14},
            'WR': {'period': 14},
            'ATR': {'period': 14},
            'OBV': {}
        }
    
    def _clean_nan_values(self, value):
        """清理NaN值，将NaN转换为None"""
        if value is None:
            return None
        try:
            # 检查是否为数值类型
            if isinstance(value, (int, float)):
                # 使用pandas的isna函数检查NaN
                if pd.isna(value):
                    return None
                # 检查是否为无穷大
                if np.isinf(value):
                    return None
            return value
        except (TypeError, ValueError):
            # 如果检查过程中出现错误，返回None
            return None
    
    def _clean_indicator_data(self, indicator_data: List[Dict]) -> List[Dict]:
        """清理指标数据中的NaN值"""
        cleaned_data = []
        for data in indicator_data:
            cleaned_item = {}
            for key, value in data.items():
                if key in ['value1', 'value2', 'value3', 'value4']:
                    cleaned_item[key] = self._clean_nan_values(value)
                else:
                    cleaned_item[key] = value
            cleaned_data.append(cleaned_item)
        return cleaned_data
    
    def _clean_results_for_json(self, results: Dict) -> Dict:
        """清理结果中的NaN值，确保JSON序列化安全"""
        import json
        import math
        
        logger.info(f"开始清理JSON结果，原始结果类型: {type(results)}")
        
        def is_nan_value(value):
            """检查是否为NaN值"""
            try:
                if value is None:
                    return False
                if isinstance(value, str):
                    return value.lower() in ['nan', 'infinity', '-infinity']
                if isinstance(value, (int, float)):
                    return pd.isna(value) or np.isnan(value) or np.isinf(value) or math.isnan(value) or math.isinf(value)
                if hasattr(value, 'item'):  # numpy标量
                    val = value.item()
                    return is_nan_value(val)
                return False
            except (TypeError, ValueError, AttributeError):
                return False
        
        def clean_value(value):
            """递归清理值中的NaN"""
            if value is None:
                return None
            elif isinstance(value, dict):
                cleaned_dict = {}
                for k, v in value.items():
                    cleaned_dict[k] = clean_value(v)
                return cleaned_dict
            elif isinstance(value, (list, tuple)):
                cleaned_list = []
                for v in value:
                    cleaned_list.append(clean_value(v))
                return cleaned_list
            elif isinstance(value, pd.Series):
                # 处理pandas Series
                cleaned_series = []
                for item in value:
                    if is_nan_value(item):
                        cleaned_series.append(None)
                    else:
                        cleaned_series.append(clean_value(item))
                return cleaned_series
            elif isinstance(value, np.ndarray):
                # 处理numpy数组
                cleaned_array = []
                for item in value.flat:
                    if is_nan_value(item):
                        cleaned_array.append(None)
                    else:
                        try:
                            cleaned_array.append(float(item) if isinstance(item, (int, float, np.number)) else item)
                        except (ValueError, TypeError):
                            cleaned_array.append(None)
                return cleaned_array
            elif is_nan_value(value):
                return None
            else:
                return value
        
        try:
            # 先清理一遍
            cleaned = clean_value(results)
            
            # 使用自定义的JSON编码器来处理剩余的NaN值
            def json_encoder(obj):
                if isinstance(obj, (np.integer, np.floating)):
                    if np.isnan(obj) or np.isinf(obj):
                        return None
                    return obj.item()
                elif isinstance(obj, np.ndarray):
                    return [json_encoder(item) for item in obj]
                elif pd.isna(obj):
                    return None
                return str(obj)
            
            # 尝试JSON序列化，如果失败则进行更深度的清理
            json_str = json.dumps(cleaned, default=json_encoder, allow_nan=False)
            
            # 如果包含NaN字符串，则替换为null
            if 'NaN' in json_str or 'Infinity' in json_str:
                logger.warning("发现JSON中包含NaN字符串，进行替换")
                json_str = json_str.replace('NaN', 'null')
                json_str = json_str.replace('Infinity', 'null')
                json_str = json_str.replace('-Infinity', 'null')
            
            # 重新解析为Python对象
            final_result = json.loads(json_str)
            
            logger.info(f"JSON清理完成，清理后结果类型: {type(final_result)}")
            return final_result
            
        except Exception as e:
            logger.error(f"JSON清理失败: {e}")
            # 如果清理失败，使用更激进的清理方法
            try:
                # 将结果转换为JSON字符串，然后替换所有NaN值
                json_str = str(results)
                json_str = json_str.replace('nan', 'null')
                json_str = json_str.replace('NaN', 'null')
                json_str = json_str.replace('Infinity', 'null')
                json_str = json_str.replace('-Infinity', 'null')
                
                # 尝试重新构建一个安全的结果
                safe_result = {
                    'success': True,
                    'data': {},
                    'message': '数据已清理NaN值',
                    'total_indicators': 0,
                    'data_points': 0,
                    'stored_records': 0
                }
                
                # 如果原始结果是字典，尝试保留一些基本信息
                if isinstance(results, dict):
                    safe_result['total_indicators'] = results.get('total_indicators', 0)
                    safe_result['data_points'] = results.get('data_points', 0)
                    safe_result['stored_records'] = results.get('stored_records', 0)
                
                return safe_result
                
            except Exception as e2:
                logger.error(f"激进清理也失败: {e2}")
                return {
                    'success': False,
                    'message': 'JSON序列化失败，数据包含无效值',
                    'error': str(e)
                }
    
    def calculate_indicators(self, ts_code: str, period_type: str, 
                           indicators: List[str] = None, 
                           lookback_days: int = 30) -> Dict:
        """
        计算指定股票的技术指标
        
        Args:
            ts_code: 股票代码
            period_type: 周期类型
            indicators: 要计算的指标列表，None表示计算所有支持的指标
            lookback_days: 回看天数
        
        Returns:
            计算结果字典
        """
        try:
            # 获取历史数据
            end_time = datetime.now()
            start_time = end_time - timedelta(days=lookback_days)
            
            data = StockMinuteData.get_data_range(
                ts_code=ts_code,
                period_type=period_type,
                start_time=start_time,
                end_time=end_time
            )
            
            if not data:
                return {'success': False, 'message': f'没有找到 {ts_code} 的数据'}
            
            # 转换为DataFrame
            df = pd.DataFrame([d.to_dict() for d in data])
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.sort_values('datetime').reset_index(drop=True)
            
            # 如果没有指定指标，计算所有支持的指标
            if indicators is None:
                indicators = list(self.supported_indicators.keys())
            
            # 计算指标
            results = {}
            indicator_data = []
            
            for indicator in indicators:
                if indicator in self.supported_indicators:
                    try:
                        indicator_result = self.supported_indicators[indicator](df)
                        results[indicator] = indicator_result
                        
                        # 准备存储数据
                        for i, row in df.iterrows():
                            if indicator in indicator_result and i < len(indicator_result[indicator]):
                                values = indicator_result[indicator][i]
                                if values is not None:
                                    # 处理单值和多值指标
                                    if isinstance(values, (int, float)):
                                        value1, value2, value3, value4 = values, None, None, None
                                    elif isinstance(values, (list, tuple)):
                                        value1 = values[0] if len(values) > 0 else None
                                        value2 = values[1] if len(values) > 1 else None
                                        value3 = values[2] if len(values) > 2 else None
                                        value4 = values[3] if len(values) > 3 else None
                                    else:
                                        continue
                                    
                                    indicator_data.append({
                                        'ts_code': ts_code,
                                        'datetime': row['datetime'],
                                        'period_type': period_type,
                                        'indicator_name': indicator,
                                        'value1': value1,
                                        'value2': value2,
                                        'value3': value3,
                                        'value4': value4
                                    })
                    except Exception as e:
                        logger.error(f"计算指标 {indicator} 失败: {str(e)}")
                        results[indicator] = {'error': str(e)}
            
            # 存储指标数据到数据库
            cleaned_indicator_data = []
            if indicator_data:
                # 删除旧数据
                RealtimeIndicator.query.filter(
                    RealtimeIndicator.ts_code == ts_code,
                    RealtimeIndicator.period_type == period_type,
                    RealtimeIndicator.datetime >= start_time
                ).delete()
                
                cleaned_indicator_data = self._clean_indicator_data(indicator_data)
                success, message = RealtimeIndicator.batch_insert(cleaned_indicator_data)
                if not success:
                    logger.error(f"存储指标数据失败: {message}")
            
            cleaned_results = self._clean_results_for_json(results)
            
            # 构建返回字典并清理整个字典
            return_dict = {
                'success': True,
                'data': cleaned_results,
                'total_indicators': len(results),
                'data_points': len(df),
                'stored_records': len(cleaned_indicator_data)
            }
            
            # 清理整个返回字典
            final_result = self._clean_results_for_json(return_dict)
            
            return final_result
            
        except Exception as e:
            logger.error(f"计算指标失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _calculate_ma(self, df: pd.DataFrame) -> Dict:
        """计算移动平均线"""
        results = {}
        periods = self.default_params['MA']['periods']
        
        for period in periods:
            if len(df) >= period:
                ma_values = df['close'].rolling(window=period).mean().tolist()
                results[f'MA{period}'] = ma_values
        
        return results
    
    def _calculate_ema(self, df: pd.DataFrame) -> Dict:
        """计算指数移动平均线"""
        results = {}
        periods = self.default_params['EMA']['periods']
        
        for period in periods:
            if len(df) >= period:
                ema_values = df['close'].ewm(span=period).mean().tolist()
                results[f'EMA{period}'] = ema_values
        
        return results
    
    def _calculate_macd(self, df: pd.DataFrame) -> Dict:
        """计算MACD指标"""
        params = self.default_params['MACD']
        fast, slow, signal = params['fast'], params['slow'], params['signal']
        
        if len(df) < slow:
            return {'MACD': [None] * len(df)}
        
        # 计算EMA
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        
        # MACD线
        macd_line = ema_fast - ema_slow
        
        # 信号线
        signal_line = macd_line.ewm(span=signal).mean()
        
        # 柱状图
        histogram = macd_line - signal_line
        
        # 组合结果 [MACD, Signal, Histogram]
        macd_values = []
        for i in range(len(df)):
            if i < slow - 1:
                macd_values.append(None)
            else:
                macd_values.append([
                    macd_line.iloc[i],
                    signal_line.iloc[i],
                    histogram.iloc[i]
                ])
        
        return {'MACD': macd_values}
    
    def _calculate_rsi(self, df: pd.DataFrame) -> Dict:
        """计算RSI指标"""
        period = self.default_params['RSI']['period']
        
        if len(df) < period + 1:
            return {'RSI': [None] * len(df)}
        
        # 计算价格变化
        delta = df['close'].diff()
        
        # 分离上涨和下跌
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # 计算平均收益和损失
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # 计算RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return {'RSI': rsi.tolist()}
    
    def _calculate_kdj(self, df: pd.DataFrame) -> Dict:
        """计算KDJ指标"""
        params = self.default_params['KDJ']
        k_period = params['k_period']
        
        if len(df) < k_period:
            return {'KDJ': [None] * len(df)}
        
        # 计算最高价和最低价的滚动窗口
        high_roll = df['high'].rolling(window=k_period)
        low_roll = df['low'].rolling(window=k_period)
        
        # 计算RSV
        rsv = (df['close'] - low_roll.min()) / (high_roll.max() - low_roll.min()) * 100
        
        # 计算K、D、J值
        k_values = []
        d_values = []
        j_values = []
        
        k_prev = 50  # K值初始值
        d_prev = 50  # D值初始值
        
        for i, rsv_val in enumerate(rsv):
            if pd.isna(rsv_val):
                k_values.append(None)
                d_values.append(None)
                j_values.append(None)
            else:
                k_val = (2/3) * k_prev + (1/3) * rsv_val
                d_val = (2/3) * d_prev + (1/3) * k_val
                j_val = 3 * k_val - 2 * d_val
                
                k_values.append(k_val)
                d_values.append(d_val)
                j_values.append(j_val)
                
                k_prev = k_val
                d_prev = d_val
        
        # 组合结果 [K, D, J]
        kdj_values = []
        for i in range(len(df)):
            if k_values[i] is None:
                kdj_values.append(None)
            else:
                kdj_values.append([k_values[i], d_values[i], j_values[i]])
        
        return {'KDJ': kdj_values}
    
    def _calculate_boll(self, df: pd.DataFrame) -> Dict:
        """计算布林带指标"""
        params = self.default_params['BOLL']
        period = params['period']
        std_dev = params['std_dev']
        
        if len(df) < period:
            return {'BOLL': [None] * len(df)}
        
        # 计算中轨（移动平均）
        middle = df['close'].rolling(window=period).mean()
        
        # 计算标准差
        std = df['close'].rolling(window=period).std()
        
        # 计算上轨和下轨
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        # 组合结果 [Upper, Middle, Lower]
        boll_values = []
        for i in range(len(df)):
            if pd.isna(middle.iloc[i]):
                boll_values.append(None)
            else:
                boll_values.append([upper.iloc[i], middle.iloc[i], lower.iloc[i]])
        
        return {'BOLL': boll_values}
    
    def _calculate_cci(self, df: pd.DataFrame) -> Dict:
        """计算CCI指标"""
        period = self.default_params['CCI']['period']
        
        if len(df) < period:
            return {'CCI': [None] * len(df)}
        
        # 计算典型价格
        tp = (df['high'] + df['low'] + df['close']) / 3
        
        # 计算移动平均
        ma_tp = tp.rolling(window=period).mean()
        
        # 计算平均绝对偏差
        mad = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        
        # 计算CCI
        cci = (tp - ma_tp) / (0.015 * mad)
        
        return {'CCI': cci.tolist()}
    
    def _calculate_wr(self, df: pd.DataFrame) -> Dict:
        """计算威廉指标"""
        period = self.default_params['WR']['period']
        
        if len(df) < period:
            return {'WR': [None] * len(df)}
        
        # 计算最高价和最低价的滚动窗口
        high_roll = df['high'].rolling(window=period)
        low_roll = df['low'].rolling(window=period)
        
        # 计算WR
        wr = (high_roll.max() - df['close']) / (high_roll.max() - low_roll.min()) * (-100)
        
        return {'WR': wr.tolist()}
    
    def _calculate_atr(self, df: pd.DataFrame) -> Dict:
        """计算平均真实波幅"""
        period = self.default_params['ATR']['period']
        
        if len(df) < 2:
            return {'ATR': [None] * len(df)}
        
        # 计算真实波幅
        high_low = df['high'] - df['low']
        high_close_prev = np.abs(df['high'] - df['close'].shift(1))
        low_close_prev = np.abs(df['low'] - df['close'].shift(1))
        
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        
        # 计算ATR
        atr = tr.rolling(window=period).mean()
        
        return {'ATR': atr.tolist()}
    
    def _calculate_obv(self, df: pd.DataFrame) -> Dict:
        """计算能量潮指标"""
        if len(df) < 2:
            return {'OBV': [None] * len(df)}
        
        # 计算价格变化
        price_change = df['close'].diff()
        
        # 计算OBV
        obv_values = [0]  # 第一个值为0
        
        for i in range(1, len(df)):
            if price_change.iloc[i] > 0:
                obv_values.append(obv_values[-1] + df['volume'].iloc[i])
            elif price_change.iloc[i] < 0:
                obv_values.append(obv_values[-1] - df['volume'].iloc[i])
            else:
                obv_values.append(obv_values[-1])
        
        return {'OBV': obv_values}
    
    def get_supported_indicators(self) -> List[Dict]:
        """获取支持的指标列表"""
        indicators = []
        for code in self.supported_indicators.keys():
            description_info = self.get_indicator_description(code)
            indicators.append({
                'code': code,
                'name': description_info['name'],
                'description': description_info['description']
            })
        return indicators
    
    def get_indicator_description(self, indicator: str) -> Dict:
        """获取指标描述"""
        descriptions = {
            'MA': {'name': '移动平均线', 'description': '简单移动平均线，平滑价格波动'},
            'EMA': {'name': '指数移动平均线', 'description': '指数加权移动平均线，对近期价格更敏感'},
            'MACD': {'name': 'MACD', 'description': '移动平均收敛发散指标，趋势跟踪指标'},
            'RSI': {'name': '相对强弱指标', 'description': '衡量价格变动速度和幅度的震荡指标'},
            'KDJ': {'name': 'KDJ随机指标', 'description': '结合动量观念、强弱指标的随机指标'},
            'BOLL': {'name': '布林带', 'description': '基于统计学的技术指标，显示价格通道'},
            'CCI': {'name': '顺势指标', 'description': '衡量价格偏离统计平均值程度的指标'},
            'WR': {'name': '威廉指标', 'description': '衡量超买超卖的震荡指标'},
            'ATR': {'name': '平均真实波幅', 'description': '衡量价格波动性的指标'},
            'OBV': {'name': '能量潮', 'description': '通过成交量变化预测价格趋势'}
        }
        
        return descriptions.get(indicator, {'name': indicator, 'description': '未知指标'})
    
    def calculate_multi_period_indicators(self, ts_code: str, 
                                        indicators: List[str] = None,
                                        periods: List[str] = None) -> Dict:
        """
        计算多周期指标
        
        Args:
            ts_code: 股票代码
            indicators: 指标列表
            periods: 周期列表
        
        Returns:
            多周期指标结果
        """
        if periods is None:
            periods = ['1min', '5min', '15min', '30min', '60min']
        
        if indicators is None:
            indicators = ['MA', 'EMA', 'MACD', 'RSI']
        
        results = {}
        
        for period in periods:
            try:
                period_result = self.calculate_indicators(
                    ts_code=ts_code,
                    period_type=period,
                    indicators=indicators,
                    lookback_days=7  # 多周期计算使用较短的回看期
                )
                results[period] = period_result
            except Exception as e:
                logger.error(f"计算 {period} 周期指标失败: {str(e)}")
                results[period] = {'success': False, 'message': str(e)}
        
        return {
            'success': True,
            'data': results,
            'ts_code': ts_code,
            'indicators': indicators,
            'periods': periods
        } 