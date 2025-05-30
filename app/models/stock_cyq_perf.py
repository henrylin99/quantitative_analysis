from app.extensions import db
from sqlalchemy import Column, String, Date, DECIMAL

class StockCyqPerf(db.Model):
    """每日筹码及胜率数据表"""
    __tablename__ = 'stock_cyq_perf'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码')
    trade_date = Column(Date, primary_key=True, comment='交易日期')
    his_low = Column(DECIMAL(10, 2), comment='历史最低价')
    his_high = Column(DECIMAL(10, 2), comment='历史最高价')
    cost_5pct = Column(DECIMAL(10, 2), comment='5%成本分位')
    cost_15pct = Column(DECIMAL(10, 2), comment='15%成本分位')
    cost_50pct = Column(DECIMAL(10, 2), comment='50%成本分位')
    cost_85pct = Column(DECIMAL(10, 2), comment='85%成本分位')
    cost_95pct = Column(DECIMAL(10, 2), comment='95%成本分位')
    weight_avg = Column(DECIMAL(10, 2), comment='加权平均成本')
    winner_rate = Column(DECIMAL(10, 2), comment='胜率')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'his_low': float(self.his_low) if self.his_low else None,
            'his_high': float(self.his_high) if self.his_high else None,
            'cost_5pct': float(self.cost_5pct) if self.cost_5pct else None,
            'cost_15pct': float(self.cost_15pct) if self.cost_15pct else None,
            'cost_50pct': float(self.cost_50pct) if self.cost_50pct else None,
            'cost_85pct': float(self.cost_85pct) if self.cost_85pct else None,
            'cost_95pct': float(self.cost_95pct) if self.cost_95pct else None,
            'weight_avg': float(self.weight_avg) if self.weight_avg else None,
            'winner_rate': float(self.winner_rate) if self.winner_rate else None
        }
    
    def __repr__(self):
        return f'<StockCyqPerf {self.ts_code} {self.trade_date}>' 