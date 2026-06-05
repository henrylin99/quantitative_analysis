"""
实时技术指标数据模型
用于存储计算出的技术指标数据
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, String, Float, DateTime, Integer, Index, func
from app import db
from app.services.parquet_event_store import ParquetEventStore


class _RealtimeIndicatorEvent:
    def __init__(self, data):
        self.__dict__.update(data)

    def to_dict(self):
        result = dict(self.__dict__)
        for key in ['datetime', 'created_at', 'updated_at']:
            value = result.get(key)
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()
        return result


class RealtimeIndicator(db.Model):
    """实时技术指标数据模型"""
    __tablename__ = 'realtime_indicators'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 基础信息
    ts_code = Column(String(10), nullable=False, comment='股票代码')
    datetime = Column(DateTime, nullable=False, comment='时间')
    period_type = Column(String(10), nullable=False, comment='周期类型: 1min, 5min, 15min, 30min, 60min')
    indicator_name = Column(String(20), nullable=False, comment='指标名称')
    
    # 指标值（支持多个值的指标）
    value1 = Column(Float, comment='指标值1')
    value2 = Column(Float, comment='指标值2') 
    value3 = Column(Float, comment='指标值3')
    value4 = Column(Float, comment='指标值4')
    
    # 元数据
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 复合索引
    __table_args__ = (
        Index('idx_indicator_ts_datetime_period', 'ts_code', 'datetime', 'period_type'),
        Index('idx_indicator_name_period', 'indicator_name', 'period_type'),
        Index('idx_indicator_datetime', 'datetime'),
    )

    @staticmethod
    def _store() -> ParquetEventStore:
        return ParquetEventStore()
    
    def __repr__(self):
        return f'<RealtimeIndicator {self.ts_code} {self.indicator_name} {self.datetime}>'
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'ts_code': self.ts_code,
            'datetime': self.datetime.isoformat() if self.datetime else None,
            'period_type': self.period_type,
            'indicator_name': self.indicator_name,
            'value1': self.value1,
            'value2': self.value2,
            'value3': self.value3,
            'value4': self.value4,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def get_latest_indicators(cls, ts_code, period_type, indicator_names=None, limit=100):
        """获取最新的技术指标数据"""
        frame = cls._store().get_latest_indicators(ts_code, period_type, indicator_names=indicator_names, limit=limit)
        return [cls._row_to_event(row) for _, row in frame.iterrows()]
    
    @classmethod
    def get_indicator_history(cls, ts_code, period_type, indicator_name, start_time=None, end_time=None):
        """获取指标历史数据"""
        frame = cls._store().get_indicator_history(
            ts_code=ts_code,
            period_type=period_type,
            indicator_name=indicator_name,
            start_time=start_time,
            end_time=end_time,
        )
        return [cls._row_to_event(row) for _, row in frame.iterrows()]
    
    @classmethod
    def batch_insert(cls, indicators_data):
        """批量插入指标数据"""
        try:
            cls._store().append_indicators(indicators_data)
            return True, f"成功插入 {len(indicators_data)} 条指标数据"
        except Exception as e:
            return False, f"批量插入失败: {str(e)}"
    
    @classmethod
    def get_indicator_stats(cls):
        """获取指标统计信息"""
        try:
            return cls._store().get_indicator_stats()
        except Exception as e:
            return {'error': str(e)}
    
    @classmethod
    def cleanup_old_data(cls, days_to_keep=30):
        """清理旧数据"""
        try:
            deleted_count = cls._store().cleanup_old_indicators(days_to_keep=days_to_keep)
            return True, f"清理了 {deleted_count} 条旧数据"
        except Exception as e:
            return False, f"清理失败: {str(e)}"

    @staticmethod
    def _row_to_event(row):
        data = row.to_dict()
        return _RealtimeIndicatorEvent(data)
