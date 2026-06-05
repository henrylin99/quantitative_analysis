"""
分钟级股票数据模型
支持1分钟、5分钟、15分钟、30分钟、60分钟等多种周期的K线数据

数据存储在 Parquet 文件中（data/stock_minute/），本类提供统一的读取接口。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd

from app.services.minute_parquet_reader import MinuteParquetReader
from app.services.minute_parquet_store import MinuteParquetStore


class StockMinuteData:
    """分钟级股票K线数据 — Parquet 代理类"""

    @classmethod
    def get_latest_data(cls, ts_code, period_type='5min', limit=100):
        """获取最新的K线数据"""
        frame = cls._reader().get_latest_data(ts_code, period_type=period_type, limit=limit)
        return [cls._row_to_event(row) for _, row in frame.iterrows()]

    @classmethod
    def get_data_by_time_range(cls, ts_code, start_time, end_time, period_type='5min'):
        """根据时间范围获取K线数据"""
        frame = cls._reader().get_data(
            ts_code=ts_code,
            period_type=period_type,
            start_time=start_time,
            end_time=end_time,
        )
        return [cls._row_to_event(row) for _, row in frame.iterrows()]

    @classmethod
    def get_data_range(cls, ts_code, period_type, start_time, end_time):
        """获取指定时间范围的数据（技术指标计算引擎使用）"""
        return cls.get_data_by_time_range(ts_code, start_time, end_time, period_type)

    @classmethod
    def get_latest_price(cls, ts_code):
        """获取最新价格（依次尝试 5min → 15min → 1min）"""
        for period in ('5min', '15min', '1min'):
            latest = cls._reader().get_latest_data(ts_code, period_type=period, limit=1)
            if not latest.empty:
                return latest.iloc[0].get("close")
        return None

    @classmethod
    def bulk_insert(cls, data_list):
        """批量插入数据"""
        try:
            frame = pd.DataFrame(data_list)
            if frame.empty:
                return True

            store = cls._store()
            if "period_type" not in frame.columns:
                store.write_frame(frame, period_type='5min')
                return True

            for period_type, period_frame in frame.groupby("period_type"):
                store.write_frame(period_frame, period_type=str(period_type))
            return True
        except Exception as e:
            raise e

    @classmethod
    def get_period_types(cls):
        """获取支持的周期类型"""
        return ['5min', '15min', '30min', '60min']

    @classmethod
    def check_data_quality(cls, ts_code, period_type='5min', hours=24):
        """检查数据质量"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        data = cls.get_data_by_time_range(ts_code, start_time, end_time, period_type)

        if not data:
            return {
                'status': 'no_data',
                'message': f'没有找到 {ts_code} 在过去 {hours} 小时的 {period_type} 数据',
                'data_count': 0,
                'missing_count': 0,
                'completeness': 0.0
            }

        if period_type == '1min':
            expected_points = hours * 60
        elif period_type == '5min':
            expected_points = hours * 12
        elif period_type == '15min':
            expected_points = hours * 4
        elif period_type == '30min':
            expected_points = hours * 2
        elif period_type == '60min':
            expected_points = hours
        else:
            expected_points = len(data)

        actual_points = len(data)
        missing_points = max(0, expected_points - actual_points)
        completeness = (actual_points / expected_points) * 100 if expected_points > 0 else 0

        return {
            'status': 'ok' if completeness > 80 else 'incomplete',
            'message': f'数据完整性: {completeness:.1f}%',
            'data_count': actual_points,
            'missing_count': missing_points,
            'completeness': completeness,
            'latest_time': data[-1].datetime.isoformat() if data else None,
            'earliest_time': data[0].datetime.isoformat() if data else None
        }

    @staticmethod
    def _reader() -> MinuteParquetReader:
        return MinuteParquetReader()

    @staticmethod
    def _store() -> MinuteParquetStore:
        return MinuteParquetStore()

    @staticmethod
    def _row_to_event(row):
        return SimpleNamespace(**row.to_dict())
