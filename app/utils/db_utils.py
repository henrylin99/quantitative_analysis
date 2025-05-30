"""
数据库工具类
适配Flask-SQLAlchemy系统，支持MySQL和SQLite双数据库
"""

import tushare as ts
import pymysql
from sqlalchemy import create_engine, text
from app.extensions import db
from config import Config
import logging

logger = logging.getLogger(__name__)

class DatabaseUtils:
    """数据库工具类，支持多种数据库连接方式"""
    
    # MySQL数据库连接信息（保持原有配置）
    _mysql_host = Config.DB_HOST
    _mysql_user = Config.DB_USER
    _mysql_password = Config.DB_PASSWORD
    _mysql_database = Config.DB_NAME
    _mysql_charset = Config.DB_CHARSET

    # Tushare API token
    _tushare_token = '0f5df633752254f28597cf54c3e1d3d662400e110cba5fa7edd99c6d'

    @classmethod
    def init_tushare_api(cls):
        """
        初始化Tushare API
        :return: Tushare pro API对象
        """
        try:
            return ts.pro_api(cls._tushare_token)
        except Exception as e:
            logger.error(f"初始化Tushare API失败: {e}")
            return None

    @classmethod
    def connect_to_mysql(cls):
        """
        连接到MySQL数据库（原有方式，用于数据迁移）
        :return: MySQL连接对象和游标
        """
        try:
            conn = pymysql.connect(
                host=cls._mysql_host,
                user=cls._mysql_user,
                password=cls._mysql_password,
                database=cls._mysql_database,
                charset=cls._mysql_charset
            )
            cursor = conn.cursor()
            logger.info("MySQL数据库连接成功")
            return conn, cursor
        except Exception as e:
            logger.error(f"MySQL数据库连接失败: {e}")
            raise e

    @classmethod
    def get_sqlalchemy_engine(cls):
        """
        获取SQLAlchemy引擎（推荐使用）
        :return: SQLAlchemy引擎对象
        """
        try:
            engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
            logger.info("SQLAlchemy引擎创建成功")
            return engine
        except Exception as e:
            logger.error(f"SQLAlchemy引擎创建失败: {e}")
            raise e

    @classmethod
    def get_flask_db(cls):
        """
        获取Flask-SQLAlchemy数据库对象（推荐使用）
        :return: Flask-SQLAlchemy db对象
        """
        return db

    @classmethod
    def test_connection(cls):
        """
        测试数据库连接
        :return: 连接状态字典
        """
        result = {
            'mysql': False,
            'sqlalchemy': False,
            'flask_db': False
        }
        
        # 测试MySQL连接
        try:
            conn, cursor = cls.connect_to_mysql()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            result['mysql'] = True
            logger.info("MySQL连接测试成功")
        except Exception as e:
            logger.error(f"MySQL连接测试失败: {e}")
        
        # 测试SQLAlchemy连接
        try:
            engine = cls.get_sqlalchemy_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            result['sqlalchemy'] = True
            logger.info("SQLAlchemy连接测试成功")
        except Exception as e:
            logger.error(f"SQLAlchemy连接测试失败: {e}")
        
        # 测试Flask-SQLAlchemy连接
        try:
            db.session.execute(text("SELECT 1"))
            result['flask_db'] = True
            logger.info("Flask-SQLAlchemy连接测试成功")
        except Exception as e:
            logger.error(f"Flask-SQLAlchemy连接测试失败: {e}")
        
        return result

    @classmethod
    def create_minute_data_tables(cls):
        """
        创建分钟数据表（如果不存在）
        使用Flask-SQLAlchemy方式
        """
        try:
            # 导入模型以确保表结构被注册
            from app.models.stock_minute_data import StockMinuteData
            
            # 创建表
            db.create_all()
            logger.info("分钟数据表创建成功")
            return True
        except Exception as e:
            logger.error(f"创建分钟数据表失败: {e}")
            return False 