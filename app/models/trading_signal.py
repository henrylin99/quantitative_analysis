"""
交易信号数据模型
用于存储实时生成的交易信号
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, String, Float, DateTime, Integer, Index, func, Text
from app import db


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
        query = cls.query.filter_by(status='ACTIVE')
        
        if ts_code:
            query = query.filter_by(ts_code=ts_code)
        if strategy_name:
            query = query.filter_by(strategy_name=strategy_name)
        
        return query.order_by(cls.datetime.desc()).limit(limit).all()
    
    @classmethod
    def get_signals_by_time_range(cls, start_time, end_time, ts_code=None, strategy_name=None):
        """根据时间范围获取交易信号"""
        query = cls.query.filter(
            cls.datetime >= start_time,
            cls.datetime <= end_time
        )
        
        if ts_code:
            query = query.filter_by(ts_code=ts_code)
        if strategy_name:
            query = query.filter_by(strategy_name=strategy_name)
        
        return query.order_by(cls.datetime.asc()).all()
    
    @classmethod
    def get_signal_performance(cls, strategy_name=None, days=30):
        """获取信号表现统计"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        query = cls.query.filter(
            cls.datetime >= start_time,
            cls.status.in_(['EXECUTED', 'EXPIRED'])
        )
        
        if strategy_name:
            query = query.filter_by(strategy_name=strategy_name)
        
        signals = query.all()
        
        if not signals:
            return {
                'total_signals': 0,
                'executed_signals': 0,
                'win_rate': 0.0,
                'avg_profit_loss': 0.0,
                'total_profit_loss': 0.0,
                'max_profit': 0.0,
                'max_loss': 0.0
            }
        
        executed_signals = [s for s in signals if s.status == 'EXECUTED' and s.profit_loss is not None]
        
        total_signals = len(signals)
        executed_count = len(executed_signals)
        
        if executed_count == 0:
            return {
                'total_signals': total_signals,
                'executed_signals': 0,
                'win_rate': 0.0,
                'avg_profit_loss': 0.0,
                'total_profit_loss': 0.0,
                'max_profit': 0.0,
                'max_loss': 0.0
            }
        
        profit_losses = [s.profit_loss for s in executed_signals]
        winning_signals = [s for s in executed_signals if s.profit_loss > 0]
        
        return {
            'total_signals': total_signals,
            'executed_signals': executed_count,
            'win_rate': len(winning_signals) / executed_count * 100,
            'avg_profit_loss': sum(profit_losses) / executed_count,
            'total_profit_loss': sum(profit_losses),
            'max_profit': max(profit_losses) if profit_losses else 0.0,
            'max_loss': min(profit_losses) if profit_losses else 0.0
        }
    
    @classmethod
    def batch_insert(cls, signals_data):
        """批量插入信号数据"""
        try:
            db.session.bulk_insert_mappings(cls, signals_data)
            db.session.commit()
            return True, f"成功插入 {len(signals_data)} 条信号数据"
        except Exception as e:
            db.session.rollback()
            return False, f"批量插入失败: {str(e)}"
    
    @classmethod
    def update_signal_status(cls, signal_id, status, executed_price=None, profit_loss=None):
        """更新信号状态"""
        try:
            signal = cls.query.get(signal_id)
            if not signal:
                return False, "信号不存在"
            
            signal.status = status
            signal.updated_at = datetime.now()
            
            if executed_price:
                signal.executed_price = executed_price
                signal.executed_time = datetime.now()
            
            if profit_loss is not None:
                signal.profit_loss = profit_loss
                if signal.trigger_price:
                    signal.profit_loss_pct = (profit_loss / signal.trigger_price) * 100
            
            db.session.commit()
            return True, "信号状态更新成功"
        except Exception as e:
            db.session.rollback()
            return False, f"更新失败: {str(e)}"
    
    @classmethod
    def expire_old_signals(cls, hours=24):
        """过期旧信号"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            expired_count = cls.query.filter(
                cls.status == 'ACTIVE',
                cls.datetime < cutoff_time
            ).update({'status': 'EXPIRED'})
            
            db.session.commit()
            return True, f"过期了 {expired_count} 条信号"
        except Exception as e:
            db.session.rollback()
            return False, f"过期信号失败: {str(e)}"
    
    @classmethod
    def get_signal_stats(cls):
        """获取信号统计信息"""
        try:
            # 总信号数
            total_signals = cls.query.count()
            
            # 按状态统计
            status_stats = db.session.query(
                cls.status,
                func.count(cls.id).label('count')
            ).group_by(cls.status).all()
            
            # 按策略统计
            strategy_stats = db.session.query(
                cls.strategy_name,
                func.count(cls.id).label('count')
            ).group_by(cls.strategy_name).all()
            
            # 按信号类型统计
            type_stats = db.session.query(
                cls.signal_type,
                func.count(cls.id).label('count')
            ).group_by(cls.signal_type).all()
            
            # 股票数量
            stock_count = db.session.query(func.count(func.distinct(cls.ts_code))).scalar()
            
            # 时间范围
            time_range = db.session.query(
                func.min(cls.datetime).label('earliest'),
                func.max(cls.datetime).label('latest')
            ).first()
            
            return {
                'total_signals': total_signals,
                'total_stocks': stock_count,
                'status_stats': {stat.status: stat.count for stat in status_stats},
                'strategy_stats': {stat.strategy_name: stat.count for stat in strategy_stats},
                'type_stats': {stat.signal_type: stat.count for stat in type_stats},
                'earliest_time': time_range.earliest.isoformat() if time_range.earliest else None,
                'latest_time': time_range.latest.isoformat() if time_range.latest else None
            }
        except Exception as e:
            return {'error': str(e)} 