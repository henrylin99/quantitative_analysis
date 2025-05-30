from app.extensions import db
from sqlalchemy import Column, String, Date, DECIMAL, BigInteger

class StockDailyHistory(db.Model):
    """股票日线行情历史数据表"""
    __tablename__ = 'stock_daily_history'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码')
    trade_date = Column(Date, primary_key=True, comment='交易日期')
    open = Column(DECIMAL(10, 2), comment='开盘价')
    high = Column(DECIMAL(10, 2), comment='最高价')
    low = Column(DECIMAL(10, 2), comment='最低价')
    close = Column(DECIMAL(10, 2), comment='收盘价')
    pre_close = Column(DECIMAL(10, 2), comment='昨收价')
    change_c = Column(DECIMAL(10, 2), comment='涨跌额')
    pct_chg = Column(DECIMAL(10, 2), comment='涨跌幅')
    vol = Column(BigInteger, comment='成交量（手）')
    amount = Column(DECIMAL(20, 2), comment='成交额（千元）')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'open': float(self.open) if self.open else None,
            'high': float(self.high) if self.high else None,
            'low': float(self.low) if self.low else None,
            'close': float(self.close) if self.close else None,
            'pre_close': float(self.pre_close) if self.pre_close else None,
            'change_c': float(self.change_c) if self.change_c else None,
            'pct_chg': float(self.pct_chg) if self.pct_chg else None,
            'vol': int(self.vol) if self.vol else None,
            'amount': float(self.amount) if self.amount else None
        }
    
    def __repr__(self):
        return f'<StockDailyHistory {self.ts_code} {self.trade_date}>' 