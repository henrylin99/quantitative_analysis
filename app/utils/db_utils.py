import tushare as ts
import pymysql
import os
from dotenv import load_dotenv


load_dotenv()


class DatabaseUtils:
    # 数据库连接信息
    _host = os.getenv('DB_HOST', '').strip()
    _user = os.getenv('DB_USER', '').strip()
    _password = os.getenv('DB_PASSWORD', '')
    _database = os.getenv('DB_NAME', '').strip()
    _charset = os.getenv('DB_CHARSET', 'utf8mb4').strip() or 'utf8mb4'

    # Tushare API token
    _tushare_token = os.getenv('TUSHARE_TOKEN') or os.getenv('tushare_token')

    @classmethod
    def _validate_db_config(cls):
        missing_keys = [
            key for key, value in {
                'DB_HOST': cls._host,
                'DB_USER': cls._user,
                'DB_PASSWORD': cls._password,
                'DB_NAME': cls._database,
            }.items() if not value
        ]
        if missing_keys:
            raise ValueError(
                f"未配置数据库连接参数: {', '.join(missing_keys)}，请在.env中设置后重试"
            )

    @classmethod
    def init_tushare_api(cls):
        """
        初始化Tushare API
        :return: Tushare pro API对象
        """
        if not cls._tushare_token:
            raise ValueError('未配置TUSHARE_TOKEN，请在.env中设置后重试')
        return ts.pro_api(cls._tushare_token)

    @classmethod
    def connect_to_mysql(cls):
        """
        连接到MySQL数据库
        :return: MySQL连接对象和游标
        """
        cls._validate_db_config()
        conn = pymysql.connect(
            host=cls._host,
            user=cls._user,
            password=cls._password,
            database=cls._database,
            charset=cls._charset
        )
        cursor = conn.cursor()
        return conn, cursor 
