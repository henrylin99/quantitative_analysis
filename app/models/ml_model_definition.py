from app.extensions import db
from sqlalchemy import Column, String, Boolean, DateTime, JSON
from datetime import datetime

class MLModelDefinition(db.Model):
    """机器学习模型定义表"""
    __tablename__ = 'ml_model_definition'
    
    model_id = Column(String(50), primary_key=True, comment='模型ID')
    model_name = Column(String(100), nullable=False, comment='模型名称')
    model_type = Column(String(30), nullable=False, comment='模型类型(random_forest/xgboost/lightgbm)')
    factor_list = Column(JSON, nullable=False, comment='使用的因子列表')
    target_type = Column(String(20), nullable=False, comment='预测目标(return_1d/return_5d/return_20d)')
    model_params = Column(JSON, comment='模型参数')
    training_config = Column(JSON, comment='训练配置')
    is_active = Column(Boolean, default=True, comment='是否启用')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'model_id': self.model_id,
            'model_name': self.model_name,
            'model_type': self.model_type,
            'factor_list': self.factor_list,
            'target_type': self.target_type,
            'model_params': self.model_params,
            'training_config': self.training_config,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<MLModelDefinition {self.model_id}: {self.model_name}>' 