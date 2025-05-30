"""
实时分析报告模型
用于存储报告模板和生成的报告记录
"""

from app.extensions import db
from datetime import datetime
from sqlalchemy import Index, Text
import json


class ReportTemplate(db.Model):
    """报告模板模型"""
    __tablename__ = 'report_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    template_name = db.Column(db.String(100), nullable=False, comment='模板名称')
    template_type = db.Column(db.String(50), nullable=False, comment='模板类型')
    description = db.Column(db.Text, comment='模板描述')
    template_config = db.Column(Text, comment='模板配置JSON')
    components = db.Column(Text, comment='组件配置JSON')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    is_default = db.Column(db.Boolean, default=False, comment='是否默认模板')
    created_by = db.Column(db.String(50), comment='创建者')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 索引
    __table_args__ = (
        Index('idx_report_templates_type', 'template_type'),
        Index('idx_report_templates_active', 'is_active'),
        Index('idx_report_templates_default', 'is_default'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'template_name': self.template_name,
            'template_type': self.template_type,
            'description': self.description,
            'template_config': json.loads(self.template_config) if self.template_config else {},
            'components': json.loads(self.components) if self.components else [],
            'is_active': self.is_active,
            'is_default': self.is_default,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def create_template(cls, template_name, template_type, description=None, 
                       template_config=None, components=None, created_by=None):
        """创建报告模板"""
        template = cls(
            template_name=template_name,
            template_type=template_type,
            description=description,
            template_config=json.dumps(template_config) if template_config else None,
            components=json.dumps(components) if components else None,
            created_by=created_by
        )
        db.session.add(template)
        db.session.commit()
        return template
    
    @classmethod
    def get_templates_by_type(cls, template_type, active_only=True):
        """根据类型获取模板"""
        query = cls.query.filter_by(template_type=template_type)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_default_template(cls, template_type):
        """获取默认模板"""
        return cls.query.filter_by(
            template_type=template_type,
            is_default=True,
            is_active=True
        ).first()


class RealtimeReport(db.Model):
    """实时分析报告模型"""
    __tablename__ = 'realtime_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    report_name = db.Column(db.String(200), nullable=False, comment='报告名称')
    report_type = db.Column(db.String(50), nullable=False, comment='报告类型')
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), comment='模板ID')
    report_content = db.Column(Text, comment='报告内容JSON')
    report_data = db.Column(Text, comment='报告数据JSON')
    report_status = db.Column(db.String(20), default='generating', comment='报告状态')
    file_path = db.Column(db.String(500), comment='文件路径')
    file_format = db.Column(db.String(20), comment='文件格式')
    file_size = db.Column(db.Integer, comment='文件大小')
    generation_time = db.Column(db.Float, comment='生成耗时(秒)')
    error_message = db.Column(db.Text, comment='错误信息')
    generated_by = db.Column(db.String(50), comment='生成者')
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, comment='生成时间')
    expires_at = db.Column(db.DateTime, comment='过期时间')
    
    # 关联
    template = db.relationship('ReportTemplate', backref='reports')
    
    # 索引
    __table_args__ = (
        Index('idx_realtime_reports_type', 'report_type'),
        Index('idx_realtime_reports_status', 'report_status'),
        Index('idx_realtime_reports_generated_at', 'generated_at'),
        Index('idx_realtime_reports_template_id', 'template_id'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'report_name': self.report_name,
            'report_type': self.report_type,
            'template_id': self.template_id,
            'template_name': self.template.template_name if self.template else None,
            'report_content': json.loads(self.report_content) if self.report_content else {},
            'report_data': json.loads(self.report_data) if self.report_data else {},
            'report_status': self.report_status,
            'file_path': self.file_path,
            'file_format': self.file_format,
            'file_size': self.file_size,
            'generation_time': self.generation_time,
            'error_message': self.error_message,
            'generated_by': self.generated_by,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }
    
    @classmethod
    def create_report(cls, report_name, report_type, template_id=None, 
                     report_content=None, report_data=None, generated_by=None):
        """创建报告"""
        report = cls(
            report_name=report_name,
            report_type=report_type,
            template_id=template_id,
            report_content=json.dumps(report_content) if report_content else None,
            report_data=json.dumps(report_data) if report_data else None,
            generated_by=generated_by
        )
        db.session.add(report)
        db.session.commit()
        return report
    
    def update_status(self, status, error_message=None, file_path=None, 
                     file_format=None, file_size=None, generation_time=None):
        """更新报告状态"""
        self.report_status = status
        if error_message:
            self.error_message = error_message
        if file_path:
            self.file_path = file_path
        if file_format:
            self.file_format = file_format
        if file_size:
            self.file_size = file_size
        if generation_time:
            self.generation_time = generation_time
        db.session.commit()
    
    @classmethod
    def get_reports_by_type(cls, report_type, limit=50):
        """根据类型获取报告"""
        return cls.query.filter_by(report_type=report_type)\
                       .order_by(cls.generated_at.desc())\
                       .limit(limit).all()
    
    @classmethod
    def get_recent_reports(cls, days=7, limit=20):
        """获取最近的报告"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return cls.query.filter(cls.generated_at >= cutoff_date)\
                       .order_by(cls.generated_at.desc())\
                       .limit(limit).all()


class ReportSubscription(db.Model):
    """报告订阅模型"""
    __tablename__ = 'report_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    subscription_name = db.Column(db.String(100), nullable=False, comment='订阅名称')
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), nullable=False, comment='模板ID')
    subscriber_email = db.Column(db.String(200), comment='订阅者邮箱')
    subscriber_phone = db.Column(db.String(20), comment='订阅者手机')
    schedule_type = db.Column(db.String(20), nullable=False, comment='调度类型')
    schedule_config = db.Column(db.Text, comment='调度配置JSON')
    notification_channels = db.Column(db.Text, comment='通知渠道JSON')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    last_sent_at = db.Column(db.DateTime, comment='最后发送时间')
    next_send_at = db.Column(db.DateTime, comment='下次发送时间')
    created_by = db.Column(db.String(50), comment='创建者')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 关联
    template = db.relationship('ReportTemplate', backref='subscriptions')
    
    # 索引
    __table_args__ = (
        Index('idx_report_subscriptions_active', 'is_active'),
        Index('idx_report_subscriptions_next_send', 'next_send_at'),
        Index('idx_report_subscriptions_template_id', 'template_id'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'subscription_name': self.subscription_name,
            'template_id': self.template_id,
            'template_name': self.template.template_name if self.template else None,
            'subscriber_email': self.subscriber_email,
            'subscriber_phone': self.subscriber_phone,
            'schedule_type': self.schedule_type,
            'schedule_config': json.loads(self.schedule_config) if self.schedule_config else {},
            'notification_channels': json.loads(self.notification_channels) if self.notification_channels else [],
            'is_active': self.is_active,
            'last_sent_at': self.last_sent_at.isoformat() if self.last_sent_at else None,
            'next_send_at': self.next_send_at.isoformat() if self.next_send_at else None,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def create_subscription(cls, subscription_name, template_id, subscriber_email=None,
                          subscriber_phone=None, schedule_type='daily', schedule_config=None,
                          notification_channels=None, created_by=None):
        """创建订阅"""
        subscription = cls(
            subscription_name=subscription_name,
            template_id=template_id,
            subscriber_email=subscriber_email,
            subscriber_phone=subscriber_phone,
            schedule_type=schedule_type,
            schedule_config=json.dumps(schedule_config) if schedule_config else None,
            notification_channels=json.dumps(notification_channels) if notification_channels else None,
            created_by=created_by
        )
        db.session.add(subscription)
        db.session.commit()
        return subscription
    
    @classmethod
    def get_pending_subscriptions(cls):
        """获取待发送的订阅"""
        now = datetime.utcnow()
        return cls.query.filter(
            cls.is_active == True,
            cls.next_send_at <= now
        ).all()
    
    def update_send_time(self):
        """更新发送时间"""
        self.last_sent_at = datetime.utcnow()
        # 根据调度类型计算下次发送时间
        if self.schedule_type == 'daily':
            from datetime import timedelta
            self.next_send_at = self.last_sent_at + timedelta(days=1)
        elif self.schedule_type == 'weekly':
            from datetime import timedelta
            self.next_send_at = self.last_sent_at + timedelta(weeks=1)
        elif self.schedule_type == 'monthly':
            from datetime import timedelta
            self.next_send_at = self.last_sent_at + timedelta(days=30)
        
        db.session.commit() 