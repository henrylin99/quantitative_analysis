"""
分钟级股票数据模型
支持1分钟、5分钟、15分钟、30分钟、60分钟等多种周期的K线数据
"""

from app.extensions import db
from datetime import datetime
from sqlalchemy import Index, func


class StockMinuteData(db.Model):
    """分钟级股票K线数据模型"""
    __tablename__ = 'stock_minute_data'
    
    id = db.Column(db.Integer, primary_key=True)
    ts_code = db.Column(db.String(20), nullable=False, comment='股票代码')
    datetime = db.Column(db.DateTime, nullable=False, comment='时间戳')
    period_type = db.Column(db.String(10), nullable=False, default='1min', comment='周期类型: 1min, 5min, 15min, 30min, 60min')
    
    # OHLCV数据
    open = db.Column(db.Float, nullable=False, comment='开盘价')
    high = db.Column(db.Float, nullable=False, comment='最高价')
    low = db.Column(db.Float, nullable=False, comment='最低价')
    close = db.Column(db.Float, nullable=False, comment='收盘价')
    volume = db.Column(db.BigInteger, nullable=False, default=0, comment='成交量')
    amount = db.Column(db.Float, nullable=False, default=0.0, comment='成交额')
    
    # 技术指标相关字段
    pre_close = db.Column(db.Float, comment='前收盘价')
    change = db.Column(db.Float, comment='涨跌额')
    pct_chg = db.Column(db.Float, comment='涨跌幅(%)')
    
    # 元数据
    created_at = db.Column(db.DateTime, default=func.now(), comment='创建时间')
    updated_at = db.Column(db.DateTime, default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 创建复合索引以提高查询性能
    __table_args__ = (
        Index('idx_ts_code_datetime_period', 'ts_code', 'datetime', 'period_type'),
        Index('idx_datetime_period', 'datetime', 'period_type'),
        Index('idx_ts_code_period', 'ts_code', 'period_type'),
    )
    
    def __repr__(self):
        return f'<StockMinuteData {self.ts_code} {self.datetime} {self.period_type}>'
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'ts_code': self.ts_code,
            'datetime': self.datetime.isoformat() if self.datetime else None,
            'period_type': self.period_type,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'amount': self.amount,
            'pre_close': self.pre_close,
            'change': self.change,
            'pct_chg': self.pct_chg,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def get_latest_data(cls, ts_code, period_type='1min', limit=100):
        """获取最新的K线数据"""
        return cls.query.filter_by(
            ts_code=ts_code,
            period_type=period_type
        ).order_by(cls.datetime.desc()).limit(limit).all()
    
    @classmethod
    def get_data_by_time_range(cls, ts_code, start_time, end_time, period_type='1min'):
        """根据时间范围获取K线数据"""
        return cls.query.filter(
            cls.ts_code == ts_code,
            cls.period_type == period_type,
            cls.datetime >= start_time,
            cls.datetime <= end_time
        ).order_by(cls.datetime.asc()).all()
    
    @classmethod
    def get_data_range(cls, ts_code, period_type, start_time, end_time):
        """获取指定时间范围的数据（技术指标计算引擎使用）"""
        return cls.get_data_by_time_range(ts_code, start_time, end_time, period_type)
    
    @classmethod
    def get_latest_price(cls, ts_code):
        """获取最新价格"""
        latest = cls.query.filter_by(
            ts_code=ts_code,
            period_type='1min'
        ).order_by(cls.datetime.desc()).first()
        return latest.close if latest else None
    
    @classmethod
    def bulk_insert(cls, data_list):
        """批量插入数据"""
        try:
            db.session.bulk_insert_mappings(cls, data_list)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e
    
    @classmethod
    def get_period_types(cls):
        """获取支持的周期类型"""
        return ['1min', '5min', '15min', '30min', '60min']
    
    @classmethod
    def check_data_quality(cls, ts_code, period_type='1min', hours=24):
        """检查数据质量"""
        from datetime import datetime, timedelta
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # 获取时间范围内的数据
        data = cls.get_data_by_time_range(ts_code, start_time, end_time, period_type)
        
        if not data:
            return {
                'status': 'no_data',
                'message': f'没有找到 {ts_code} 在过去 {hours} 小时的 {period_type} 数据',
                'data_count': 0,
                'missing_count': 0,
                'completeness': 0.0
            }
        
        # 计算预期数据点数量（简化计算，实际需要考虑交易时间）
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