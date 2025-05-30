from app.extensions import db
from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON
from datetime import datetime

class FactorDefinition(db.Model):
    """自定义因子定义表"""
    __tablename__ = 'factor_definition'
    
    factor_id = Column(String(50), primary_key=True, comment='因子ID')
    factor_name = Column(String(100), nullable=False, comment='因子名称')
    factor_formula = Column(Text, nullable=False, comment='因子公式')
    factor_type = Column(String(20), nullable=False, comment='因子类型(technical/fundamental/momentum/volatility)')
    description = Column(Text, comment='因子描述')
    params = Column(JSON, comment='参数配置')
    is_active = Column(Boolean, default=True, comment='是否启用')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'factor_id': self.factor_id,
            'factor_name': self.factor_name,
            'factor_formula': self.factor_formula,
            'factor_type': self.factor_type,
            'description': self.description,
            'params': self.params,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<FactorDefinition {self.factor_id}: {self.factor_name}>' 