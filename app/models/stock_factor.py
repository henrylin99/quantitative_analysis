from app.extensions import db
from sqlalchemy import Column, String, Date, DECIMAL

class StockFactor(db.Model):
    """股票技术面因子数据表"""
    __tablename__ = 'stock_factor'
    
    ts_code = Column(String(20), primary_key=True, comment='股票代码')
    trade_date = Column(Date, primary_key=True, comment='交易日期')
    close = Column(DECIMAL(10, 2), comment='收盘价')
    open = Column(DECIMAL(10, 2), comment='开盘价')
    high = Column(DECIMAL(10, 2), comment='最高价')
    low = Column(DECIMAL(10, 2), comment='最低价')
    pre_close = Column(DECIMAL(10, 2), comment='昨收价')
    change = Column(DECIMAL(10, 2), comment='涨跌额')
    pct_change = Column(DECIMAL(10, 2), comment='涨跌幅')
    vol = Column(DECIMAL(20, 2), comment='成交量')
    amount = Column(DECIMAL(20, 2), comment='成交额')
    adj_factor = Column(DECIMAL(10, 2), comment='复权因子')
    
    # 复权价格
    open_hfq = Column(DECIMAL(10, 2), comment='后复权开盘价')
    open_qfq = Column(DECIMAL(10, 2), comment='前复权开盘价')
    close_hfq = Column(DECIMAL(10, 2), comment='后复权收盘价')
    close_qfq = Column(DECIMAL(10, 2), comment='前复权收盘价')
    high_hfq = Column(DECIMAL(10, 2), comment='后复权最高价')
    high_qfq = Column(DECIMAL(10, 2), comment='前复权最高价')
    low_hfq = Column(DECIMAL(10, 2), comment='后复权最低价')
    low_qfq = Column(DECIMAL(10, 2), comment='前复权最低价')
    pre_close_hfq = Column(DECIMAL(10, 2), comment='后复权昨收价')
    pre_close_qfq = Column(DECIMAL(10, 2), comment='前复权昨收价')
    
    # 技术指标
    macd_dif = Column(DECIMAL(10, 2), comment='MACD DIF值')
    macd_dea = Column(DECIMAL(10, 2), comment='MACD DEA值')
    macd = Column(DECIMAL(10, 2), comment='MACD值')
    kdj_k = Column(DECIMAL(10, 2), comment='KDJ K值')
    kdj_d = Column(DECIMAL(10, 2), comment='KDJ D值')
    kdj_j = Column(DECIMAL(10, 2), comment='KDJ J值')
    rsi_6 = Column(DECIMAL(10, 2), comment='RSI 6日')
    rsi_12 = Column(DECIMAL(10, 2), comment='RSI 12日')
    rsi_24 = Column(DECIMAL(10, 2), comment='RSI 24日')
    boll_upper = Column(DECIMAL(10, 2), comment='布林上轨')
    boll_mid = Column(DECIMAL(10, 2), comment='布林中轨')
    boll_lower = Column(DECIMAL(10, 2), comment='布林下轨')
    cci = Column(DECIMAL(10, 2), comment='CCI指标')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'close': float(self.close) if self.close else None,
            'open': float(self.open) if self.open else None,
            'high': float(self.high) if self.high else None,
            'low': float(self.low) if self.low else None,
            'pre_close': float(self.pre_close) if self.pre_close else None,
            'change': float(self.change) if self.change else None,
            'pct_change': float(self.pct_change) if self.pct_change else None,
            'vol': float(self.vol) if self.vol else None,
            'amount': float(self.amount) if self.amount else None,
            'adj_factor': float(self.adj_factor) if self.adj_factor else None,
            'open_hfq': float(self.open_hfq) if self.open_hfq else None,
            'close_hfq': float(self.close_hfq) if self.close_hfq else None,
            'high_hfq': float(self.high_hfq) if self.high_hfq else None,
            'low_hfq': float(self.low_hfq) if self.low_hfq else None,
            'macd_dif': float(self.macd_dif) if self.macd_dif else None,
            'macd_dea': float(self.macd_dea) if self.macd_dea else None,
            'macd': float(self.macd) if self.macd else None,
            'kdj_k': float(self.kdj_k) if self.kdj_k else None,
            'kdj_d': float(self.kdj_d) if self.kdj_d else None,
            'kdj_j': float(self.kdj_j) if self.kdj_j else None,
            'rsi_6': float(self.rsi_6) if self.rsi_6 else None,
            'rsi_12': float(self.rsi_12) if self.rsi_12 else None,
            'rsi_24': float(self.rsi_24) if self.rsi_24 else None,
            'boll_upper': float(self.boll_upper) if self.boll_upper else None,
            'boll_mid': float(self.boll_mid) if self.boll_mid else None,
            'boll_lower': float(self.boll_lower) if self.boll_lower else None,
            'cci': float(self.cci) if self.cci else None
        }
    
    def __repr__(self):
        return f'<StockFactor {self.ts_code} {self.trade_date}>' 