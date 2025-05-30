"""
风险预警记录模型
用于存储风险预警信息和历史记录
"""

from app.extensions import db
from datetime import datetime
from sqlalchemy import Index


class RiskAlert(db.Model):
    """风险预警记录模型"""
    __tablename__ = 'risk_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    ts_code = db.Column(db.String(20), nullable=False, comment='股票代码')
    alert_type = db.Column(db.String(50), nullable=False, comment='预警类型')
    alert_level = db.Column(db.String(20), nullable=False, comment='预警级别')
    alert_message = db.Column(db.Text, comment='预警消息')
    risk_value = db.Column(db.Float, comment='风险值')
    threshold_value = db.Column(db.Float, comment='阈值')
    current_price = db.Column(db.Float, comment='当前价格')
    position_size = db.Column(db.Float, comment='持仓数量')
    portfolio_weight = db.Column(db.Float, comment='组合权重')
    is_active = db.Column(db.Boolean, default=True, comment='是否活跃')
    is_resolved = db.Column(db.Boolean, default=False, comment='是否已解决')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    resolved_at = db.Column(db.DateTime, comment='解决时间')
    
    # 复合索引
    __table_args__ = (
        Index('idx_risk_alerts_ts_code_type', 'ts_code', 'alert_type'),
        Index('idx_risk_alerts_level_active', 'alert_level', 'is_active'),
        Index('idx_risk_alerts_created_at', 'created_at'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'ts_code': self.ts_code,
            'alert_type': self.alert_type,
            'alert_level': self.alert_level,
            'alert_message': self.alert_message,
            'risk_value': self.risk_value,
            'threshold_value': self.threshold_value,
            'current_price': self.current_price,
            'position_size': self.position_size,
            'portfolio_weight': self.portfolio_weight,
            'is_active': self.is_active,
            'is_resolved': self.is_resolved,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }
    
    @classmethod
    def create_alert(cls, ts_code, alert_type, alert_level, alert_message, 
                    risk_value=None, threshold_value=None, current_price=None,
                    position_size=None, portfolio_weight=None):
        """创建风险预警"""
        alert = cls(
            ts_code=ts_code,
            alert_type=alert_type,
            alert_level=alert_level,
            alert_message=alert_message,
            risk_value=risk_value,
            threshold_value=threshold_value,
            current_price=current_price,
            position_size=position_size,
            portfolio_weight=portfolio_weight
        )
        db.session.add(alert)
        db.session.commit()
        return alert
    
    def resolve_alert(self):
        """解决预警"""
        self.is_resolved = True
        self.is_active = False
        self.resolved_at = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def get_active_alerts(cls, ts_code=None, alert_type=None, alert_level=None):
        """获取活跃预警"""
        query = cls.query.filter_by(is_active=True, is_resolved=False)
        
        if ts_code:
            query = query.filter_by(ts_code=ts_code)
        if alert_type:
            query = query.filter_by(alert_type=alert_type)
        if alert_level:
            query = query.filter_by(alert_level=alert_level)
            
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_alert_stats(cls):
        """获取预警统计"""
        from sqlalchemy import func
        
        stats = db.session.query(
            cls.alert_level,
            func.count(cls.id).label('count')
        ).filter_by(is_active=True, is_resolved=False).group_by(cls.alert_level).all()
        
        return {level: count for level, count in stats} 