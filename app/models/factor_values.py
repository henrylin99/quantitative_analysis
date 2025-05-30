from app.extensions import db
from sqlalchemy import Column, String, Date, DECIMAL, DateTime, Index
from datetime import datetime

class FactorValues(db.Model):
    """因子计算结果表"""
    __tablename__ = 'factor_values'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码')
    trade_date = Column(Date, primary_key=True, comment='交易日期')
    factor_id = Column(String(50), primary_key=True, comment='因子ID')
    factor_value = Column(DECIMAL(15, 6), comment='因子值')
    percentile_rank = Column(DECIMAL(5, 2), comment='百分位排名')
    z_score = Column(DECIMAL(10, 4), comment='Z分数')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    
    # 创建索引
    __table_args__ = (
        Index('idx_factor_date', 'factor_id', 'trade_date'),
        Index('idx_date_factor', 'trade_date', 'factor_id'),
        Index('idx_ts_code_date', 'ts_code', 'trade_date'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'factor_id': self.factor_id,
            'factor_value': float(self.factor_value) if self.factor_value else None,
            'percentile_rank': float(self.percentile_rank) if self.percentile_rank else None,
            'z_score': float(self.z_score) if self.z_score else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<FactorValues {self.ts_code} {self.trade_date} {self.factor_id}>' 