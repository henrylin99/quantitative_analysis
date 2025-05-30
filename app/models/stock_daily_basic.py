from app.extensions import db
from sqlalchemy import Column, String, Date, DECIMAL

class StockDailyBasic(db.Model):
    """股票日线基本数据表"""
    __tablename__ = 'stock_daily_basic'
    
    ts_code = Column(String(20), primary_key=True, comment='TS股票代码')
    trade_date = Column(Date, primary_key=True, comment='交易日期')
    close = Column(DECIMAL(10, 2), comment='当日收盘价')
    turnover_rate = Column(DECIMAL(10, 2), comment='换手率（%）')
    turnover_rate_f = Column(DECIMAL(10, 2), comment='换手率（自由流通股）')
    volume_ratio = Column(DECIMAL(10, 2), comment='量比')
    pe = Column(DECIMAL(10, 2), comment='市盈率')
    pe_ttm = Column(DECIMAL(10, 2), comment='市盈率（TTM）')
    pb = Column(DECIMAL(10, 2), comment='市净率')
    ps = Column(DECIMAL(10, 2), comment='市销率')
    ps_ttm = Column(DECIMAL(10, 2), comment='市销率（TTM）')
    dv_ratio = Column(DECIMAL(10, 2), comment='股息率（%）')
    dv_ttm = Column(DECIMAL(10, 2), comment='股息率（TTM）（%）')
    total_share = Column(DECIMAL(20, 2), comment='总股本（万股）')
    float_share = Column(DECIMAL(20, 2), comment='流通股本（万股）')
    free_share = Column(DECIMAL(20, 2), comment='自由流通股本（万）')
    total_mv = Column(DECIMAL(20, 2), comment='总市值（万元）')
    circ_mv = Column(DECIMAL(20, 2), comment='流通市值（万元）')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'close': float(self.close) if self.close else None,
            'turnover_rate': float(self.turnover_rate) if self.turnover_rate else None,
            'turnover_rate_f': float(self.turnover_rate_f) if self.turnover_rate_f else None,
            'volume_ratio': float(self.volume_ratio) if self.volume_ratio else None,
            'pe': float(self.pe) if self.pe else None,
            'pe_ttm': float(self.pe_ttm) if self.pe_ttm else None,
            'pb': float(self.pb) if self.pb else None,
            'ps': float(self.ps) if self.ps else None,
            'ps_ttm': float(self.ps_ttm) if self.ps_ttm else None,
            'dv_ratio': float(self.dv_ratio) if self.dv_ratio else None,
            'dv_ttm': float(self.dv_ttm) if self.dv_ttm else None,
            'total_share': float(self.total_share) if self.total_share else None,
            'float_share': float(self.float_share) if self.float_share else None,
            'free_share': float(self.free_share) if self.free_share else None,
            'total_mv': float(self.total_mv) if self.total_mv else None,
            'circ_mv': float(self.circ_mv) if self.circ_mv else None
        }
    
    def __repr__(self):
        return f'<StockDailyBasic {self.ts_code} {self.trade_date}>' 