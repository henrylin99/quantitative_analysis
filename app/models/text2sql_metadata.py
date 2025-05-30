"""
Text2SQL元数据模型
用于管理数据库表结构、字段映射、查询模板等元数据信息
"""

from app.extensions import db
from datetime import datetime
import json


class TableMetadata(db.Model):
    """表元数据"""
    __tablename__ = 'table_metadata'
    
    table_name = db.Column(db.String(100), primary_key=True, comment='表名')
    table_alias = db.Column(db.String(100), comment='表别名')
    description = db.Column(db.Text, comment='表描述')
    business_domain = db.Column(db.String(50), comment='业务域(技术面、基本面、资金面等)')
    is_active = db.Column(db.Boolean, default=True, comment='是否激活')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 关联字段元数据
    fields = db.relationship('FieldMetadata', backref='table', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'table_name': self.table_name,
            'table_alias': self.table_alias,
            'description': self.description,
            'business_domain': self.business_domain,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class FieldMetadata(db.Model):
    """字段元数据"""
    __tablename__ = 'field_metadata'
    
    table_name = db.Column(db.String(100), db.ForeignKey('table_metadata.table_name'), primary_key=True, comment='表名')
    field_name = db.Column(db.String(100), primary_key=True, comment='字段名')
    field_alias = db.Column(db.String(100), comment='字段别名')
    field_type = db.Column(db.String(50), comment='字段类型')
    description = db.Column(db.Text, comment='字段描述')
    business_meaning = db.Column(db.Text, comment='业务含义')
    synonyms = db.Column(db.JSON, comment='同义词列表')
    is_active = db.Column(db.Boolean, default=True, comment='是否激活')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'table_name': self.table_name,
            'field_name': self.field_name,
            'field_alias': self.field_alias,
            'field_type': self.field_type,
            'description': self.description,
            'business_meaning': self.business_meaning,
            'synonyms': self.synonyms,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class QueryTemplate(db.Model):
    """查询模板"""
    __tablename__ = 'query_template'
    
    template_id = db.Column(db.String(50), primary_key=True, comment='模板ID')
    template_name = db.Column(db.String(100), nullable=False, comment='模板名称')
    intent_pattern = db.Column(db.Text, comment='意图匹配模式')
    sql_template = db.Column(db.Text, comment='SQL模板')
    parameters = db.Column(db.JSON, comment='参数定义')
    usage_count = db.Column(db.Integer, default=0, comment='使用次数')
    is_active = db.Column(db.Boolean, default=True, comment='是否激活')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'template_id': self.template_id,
            'template_name': self.template_name,
            'intent_pattern': self.intent_pattern,
            'sql_template': self.sql_template,
            'parameters': self.parameters,
            'usage_count': self.usage_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def increment_usage(self):
        """增加使用次数"""
        self.usage_count += 1
        db.session.commit()


class QueryHistory(db.Model):
    """查询历史"""
    __tablename__ = 'query_history'
    
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    user_query = db.Column(db.Text, nullable=False, comment='用户查询')
    intent = db.Column(db.String(50), comment='识别意图')
    entities = db.Column(db.JSON, comment='提取的实体')
    generated_sql = db.Column(db.Text, comment='生成的SQL')
    execution_time = db.Column(db.Numeric(10, 3), comment='执行时间(秒)')
    result_count = db.Column(db.Integer, comment='结果数量')
    is_successful = db.Column(db.Boolean, comment='是否成功')
    error_message = db.Column(db.Text, comment='错误信息')
    template_used = db.Column(db.String(50), comment='使用的模板ID')
    user_ip = db.Column(db.String(45), comment='用户IP')
    user_agent = db.Column(db.String(500), comment='用户代理')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_query': self.user_query,
            'intent': self.intent,
            'entities': self.entities,
            'generated_sql': self.generated_sql,
            'execution_time': float(self.execution_time) if self.execution_time else None,
            'result_count': self.result_count,
            'is_successful': self.is_successful,
            'error_message': self.error_message,
            'template_used': self.template_used,
            'user_ip': self.user_ip,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class BusinessDictionary(db.Model):
    """业务词典"""
    __tablename__ = 'business_dictionary'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='主键ID')
    category = db.Column(db.String(50), nullable=False, comment='词典分类')
    standard_term = db.Column(db.String(100), nullable=False, comment='标准术语')
    synonyms = db.Column(db.JSON, comment='同义词列表')
    description = db.Column(db.Text, comment='术语描述')
    mapping_field = db.Column(db.String(100), comment='映射字段')
    mapping_table = db.Column(db.String(100), comment='映射表')
    is_active = db.Column(db.Boolean, default=True, comment='是否激活')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'category': self.category,
            'standard_term': self.standard_term,
            'synonyms': self.synonyms,
            'description': self.description,
            'mapping_field': self.mapping_field,
            'mapping_table': self.mapping_table,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        } 