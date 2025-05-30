from app.extensions import db
from sqlalchemy import Column, String, DECIMAL

class StockMaData(db.Model):
    """股票移动平均线数据表"""
    __tablename__ = 'stock_ma_data'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码')
    ma5 = Column(DECIMAL(10, 3), comment='5日移动平均线')
    ma10 = Column(DECIMAL(10, 3), comment='10日移动平均线')
    ma20 = Column(DECIMAL(10, 3), comment='20日移动平均线')
    ma30 = Column(DECIMAL(10, 3), comment='30日移动平均线')
    ma60 = Column(DECIMAL(10, 3), comment='60日移动平均线')
    ma120 = Column(DECIMAL(10, 3), comment='120日移动平均线')
    ema5 = Column(DECIMAL(10, 3), comment='5日指数移动平均线')
    ema10 = Column(DECIMAL(10, 3), comment='10日指数移动平均线')
    ema20 = Column(DECIMAL(10, 3), comment='20日指数移动平均线')
    ema30 = Column(DECIMAL(10, 3), comment='30日指数移动平均线')
    ema60 = Column(DECIMAL(10, 3), comment='60日指数移动平均线')
    ema120 = Column(DECIMAL(10, 3), comment='120日指数移动平均线')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'ma5': float(self.ma5) if self.ma5 else None,
            'ma10': float(self.ma10) if self.ma10 else None,
            'ma20': float(self.ma20) if self.ma20 else None,
            'ma30': float(self.ma30) if self.ma30 else None,
            'ma60': float(self.ma60) if self.ma60 else None,
            'ma120': float(self.ma120) if self.ma120 else None,
            'ema5': float(self.ema5) if self.ema5 else None,
            'ema10': float(self.ema10) if self.ema10 else None,
            'ema20': float(self.ema20) if self.ema20 else None,
            'ema30': float(self.ema30) if self.ema30 else None,
            'ema60': float(self.ema60) if self.ema60 else None,
            'ema120': float(self.ema120) if self.ema120 else None
        }
    
    def __repr__(self):
        return f'<StockMaData {self.ts_code}>' 