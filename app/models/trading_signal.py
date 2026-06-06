"""
交易信号数据模型
用于存储实时生成的交易信号
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, String, Float, DateTime, Integer, Index, func, Text
from app import db
from app.services.parquet_event_store import ParquetEventStore


class _TradingSignalEvent:
    def __init__(self, data):
        self.__dict__.update(data)

    def to_dict(self):
        import math
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, float) and math.isnan(value):
                result[key] = None
            elif hasattr(value, 'isoformat'):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result


class TradingSignal(db.Model):
    """交易信号数据模型"""
    __tablename__ = 'trading_signals'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 基础信息
    ts_code = Column(String(10), nullable=False, comment='股票代码')
    datetime = Column(DateTime, nullable=False, comment='信号生成时间')
    period_type = Column(String(10), nullable=False, comment='周期类型: 1min, 5min, 15min, 30min, 60min')
    
    # 信号信息
    strategy_name = Column(String(50), nullable=False, comment='策略名称')
    signal_type = Column(String(20), nullable=False, comment='信号类型: BUY, SELL, HOLD')
    signal_strength = Column(Float, nullable=False, comment='信号强度: -1.0到1.0，负数为卖出，正数为买入')
    confidence = Column(Float, nullable=False, comment='置信度: 0.0到1.0')
    
    # 价格信息
    trigger_price = Column(Float, nullable=False, comment='触发价格')
    target_price = Column(Float, comment='目标价格')
    stop_loss_price = Column(Float, comment='止损价格')
    
    # 策略参数
    strategy_params = Column(Text, comment='策略参数JSON')
    indicators_used = Column(Text, comment='使用的技术指标JSON')
    
    # 信号状态
    status = Column(String(20), default='ACTIVE', comment='信号状态: ACTIVE, EXPIRED, EXECUTED, CANCELLED')
    expiry_time = Column(DateTime, comment='信号过期时间')
    
    # 执行信息
    executed_price = Column(Float, comment='实际执行价格')
    executed_time = Column(DateTime, comment='执行时间')
    profit_loss = Column(Float, comment='盈亏金额')
    profit_loss_pct = Column(Float, comment='盈亏百分比')
    
    # 元数据
    created_at = Column(DateTime, default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 复合索引
    __table_args__ = (
        Index('idx_signal_ts_datetime_period', 'ts_code', 'datetime', 'period_type'),
        Index('idx_signal_strategy_type', 'strategy_name', 'signal_type'),
        Index('idx_signal_datetime_status', 'datetime', 'status'),
        Index('idx_signal_strength', 'signal_strength'),
    )

    @staticmethod
    def _store() -> ParquetEventStore:
        return ParquetEventStore()
    
    def __repr__(self):
        return f'<TradingSignal {self.ts_code} {self.strategy_name} {self.signal_type} {self.datetime}>'
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'ts_code': self.ts_code,
            'datetime': self.datetime.isoformat() if self.datetime else None,
            'period_type': self.period_type,
            'strategy_name': self.strategy_name,
            'signal_type': self.signal_type,
            'signal_strength': self.signal_strength,
            'confidence': self.confidence,
            'trigger_price': self.trigger_price,
            'target_price': self.target_price,
            'stop_loss_price': self.stop_loss_price,
            'strategy_params': self.strategy_params,
            'indicators_used': self.indicators_used,
            'status': self.status,
            'expiry_time': self.expiry_time.isoformat() if self.expiry_time else None,
            'executed_price': self.executed_price,
            'executed_time': self.executed_time.isoformat() if self.executed_time else None,
            'profit_loss': self.profit_loss,
            'profit_loss_pct': self.profit_loss_pct,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def get_active_signals(cls, ts_code=None, strategy_name=None, limit=100):
        """获取活跃的交易信号"""
        frame = cls._store().get_active_signals(ts_code=ts_code, strategy_name=strategy_name, limit=limit)
        return [cls._row_to_event(row) for _, row in frame.iterrows()]
    
    @classmethod
    def get_signals_by_time_range(cls, start_time, end_time, ts_code=None, strategy_name=None):
        """根据时间范围获取交易信号"""
        frame = cls._store().get_signals_by_time_range(
            start_time=start_time,
            end_time=end_time,
            ts_code=ts_code,
            strategy_name=strategy_name,
        )
        return [cls._row_to_event(row) for _, row in frame.iterrows()]
    
    @classmethod
    def get_signal_performance(cls, strategy_name=None, days=30):
        """获取信号表现统计"""
        return cls._store().get_signal_performance(strategy_name=strategy_name, days=days)
    
    @classmethod
    def batch_insert(cls, signals_data):
        """批量插入信号数据"""
        try:
            cls._store().append_signals(signals_data)
            return True, f"成功插入 {len(signals_data)} 条信号数据"
        except Exception as e:
            return False, f"批量插入失败: {str(e)}"
    
    @classmethod
    def update_signal_status(cls, signal_id, status, executed_price=None, profit_loss=None):
        """更新信号状态"""
        try:
            success = cls._store().update_signal_status(
                signal_id,
                status,
                executed_price=executed_price,
                profit_loss=profit_loss,
            )
            return (True, "信号状态更新成功") if success else (False, "信号不存在")
        except Exception as e:
            return False, f"更新失败: {str(e)}"
    
    @classmethod
    def expire_old_signals(cls, hours=24):
        """过期旧信号"""
        try:
            expired_count = cls._store().expire_old_signals(hours=hours)
            return True, f"过期了 {expired_count} 条信号"
        except Exception as e:
            return False, f"过期信号失败: {str(e)}"
    
    @classmethod
    def get_signal_stats(cls):
        """获取信号统计信息"""
        try:
            return cls._store().get_signal_stats()
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def _row_to_event(row):
        data = row.to_dict()
        return _TradingSignalEvent(data)
