from app.extensions import db
from sqlalchemy import Column, String, Date

class StockBasic(db.Model):
    """股票公司基本信息表"""
    __tablename__ = 'stock_basic'
    
    ts_code = Column(String(20), primary_key=True, comment='TS代码')
    symbol = Column(String(20), comment='股票代码')
    name = Column(String(100), comment='股票名称')
    area = Column(String(100), comment='地域')
    industry = Column(String(100), comment='所属行业')
    list_date = Column(Date, comment='上市日期')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'ts_code': self.ts_code,
            'symbol': self.symbol,
            'name': self.name,
            'area': self.area,
            'industry': self.industry,
            'list_date': self.list_date.isoformat() if self.list_date else None
        }
    
    def __repr__(self):
        return f'<StockBasic {self.ts_code}: {self.name}>' 