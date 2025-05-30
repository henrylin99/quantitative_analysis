"""
投资组合持仓模型
用于存储和管理投资组合的持仓信息
"""

from app.extensions import db
from datetime import datetime
from sqlalchemy import Index


class PortfolioPosition(db.Model):
    """投资组合持仓模型"""
    __tablename__ = 'portfolio_positions'
    
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.String(50), nullable=False, comment='组合ID')
    ts_code = db.Column(db.String(20), nullable=False, comment='股票代码')
    position_size = db.Column(db.Float, nullable=False, comment='持仓数量')
    avg_cost = db.Column(db.Float, nullable=False, comment='平均成本')
    current_price = db.Column(db.Float, comment='当前价格')
    market_value = db.Column(db.Float, comment='市值')
    unrealized_pnl = db.Column(db.Float, comment='浮动盈亏')
    weight = db.Column(db.Float, comment='权重')
    sector = db.Column(db.String(50), comment='行业')
    market_cap = db.Column(db.Float, comment='市值规模')
    beta = db.Column(db.Float, comment='Beta值')
    volatility = db.Column(db.Float, comment='波动率')
    var_1d = db.Column(db.Float, comment='1日VaR')
    var_5d = db.Column(db.Float, comment='5日VaR')
    stop_loss_price = db.Column(db.Float, comment='止损价格')
    take_profit_price = db.Column(db.Float, comment='止盈价格')
    is_active = db.Column(db.Boolean, default=True, comment='是否活跃')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 复合索引
    __table_args__ = (
        Index('idx_portfolio_positions_portfolio_id', 'portfolio_id'),
        Index('idx_portfolio_positions_ts_code', 'ts_code'),
        Index('idx_portfolio_positions_portfolio_ts_code', 'portfolio_id', 'ts_code'),
        Index('idx_portfolio_positions_active', 'is_active'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'portfolio_id': self.portfolio_id,
            'ts_code': self.ts_code,
            'position_size': self.position_size,
            'avg_cost': self.avg_cost,
            'current_price': self.current_price,
            'market_value': self.market_value,
            'unrealized_pnl': self.unrealized_pnl,
            'weight': self.weight,
            'sector': self.sector,
            'market_cap': self.market_cap,
            'beta': self.beta,
            'volatility': self.volatility,
            'var_1d': self.var_1d,
            'var_5d': self.var_5d,
            'stop_loss_price': self.stop_loss_price,
            'take_profit_price': self.take_profit_price,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def update_market_data(self, current_price):
        """更新市场数据"""
        self.current_price = current_price
        self.market_value = self.position_size * current_price
        self.unrealized_pnl = (current_price - self.avg_cost) * self.position_size
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def calculate_pnl_percentage(self):
        """计算盈亏百分比"""
        if self.avg_cost and self.avg_cost > 0:
            return (self.current_price - self.avg_cost) / self.avg_cost * 100
        return 0.0
    
    def is_stop_loss_triggered(self):
        """检查是否触发止损"""
        if self.stop_loss_price and self.current_price:
            return self.current_price <= self.stop_loss_price
        return False
    
    def is_take_profit_triggered(self):
        """检查是否触发止盈"""
        if self.take_profit_price and self.current_price:
            return self.current_price >= self.take_profit_price
        return False
    
    @classmethod
    def get_portfolio_positions(cls, portfolio_id, active_only=True):
        """获取组合持仓"""
        query = cls.query.filter_by(portfolio_id=portfolio_id)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.all()
    
    @classmethod
    def get_position_by_stock(cls, portfolio_id, ts_code):
        """获取特定股票的持仓"""
        return cls.query.filter_by(
            portfolio_id=portfolio_id,
            ts_code=ts_code,
            is_active=True
        ).first()
    
    @classmethod
    def calculate_portfolio_metrics(cls, portfolio_id):
        """计算组合指标"""
        positions = cls.get_portfolio_positions(portfolio_id)
        
        if not positions:
            return {}
        
        total_market_value = sum(pos.market_value or 0 for pos in positions)
        total_unrealized_pnl = sum(pos.unrealized_pnl or 0 for pos in positions)
        
        # 计算权重
        for pos in positions:
            if total_market_value > 0:
                pos.weight = (pos.market_value or 0) / total_market_value * 100
        
        # 行业分布
        sector_distribution = {}
        for pos in positions:
            sector = pos.sector or '未知'
            if sector not in sector_distribution:
                sector_distribution[sector] = 0
            sector_distribution[sector] += pos.weight or 0
        
        # 风险指标
        portfolio_var_1d = sum((pos.var_1d or 0) * (pos.weight or 0) / 100 for pos in positions)
        portfolio_var_5d = sum((pos.var_5d or 0) * (pos.weight or 0) / 100 for pos in positions)
        
        return {
            'total_positions': len(positions),
            'total_market_value': total_market_value,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_pnl_percentage': (total_unrealized_pnl / (total_market_value - total_unrealized_pnl) * 100) if total_market_value > total_unrealized_pnl else 0,
            'sector_distribution': sector_distribution,
            'portfolio_var_1d': portfolio_var_1d,
            'portfolio_var_5d': portfolio_var_5d,
            'max_position_weight': max((pos.weight or 0) for pos in positions) if positions else 0,
            'positions': [pos.to_dict() for pos in positions]
        } 