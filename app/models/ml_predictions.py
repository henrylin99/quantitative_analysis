from app.extensions import db
from sqlalchemy import Column, String, Date, DECIMAL, Integer, DateTime, Index
from datetime import datetime

class MLPredictions(db.Model):
    """模型预测结果表"""
    __tablename__ = 'ml_predictions'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码')
    trade_date = Column(Date, primary_key=True, comment='交易日期')
    model_id = Column(String(50), primary_key=True, comment='模型ID')
    predicted_return = Column(DECIMAL(10, 4), comment='预测收益率')
    probability_score = Column(DECIMAL(10, 4), comment='概率分数')
    rank_score = Column(Integer, comment='排名分数')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    
    # 创建索引
    __table_args__ = (
        Index('idx_model_date', 'model_id', 'trade_date'),
        Index('idx_date_rank', 'trade_date', 'rank_score'),
        Index('idx_ts_code_date', 'ts_code', 'trade_date'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'model_id': self.model_id,
            'predicted_return': float(self.predicted_return) if self.predicted_return else None,
            'probability_score': float(self.probability_score) if self.probability_score else None,
            'rank_score': self.rank_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<MLPredictions {self.ts_code} {self.trade_date} {self.model_id}>' 