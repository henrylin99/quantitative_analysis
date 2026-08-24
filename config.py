import os
from dotenv import load_dotenv
from datetime import timedelta

# 加载环境变量
load_dotenv()


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _build_sqlalchemy_engine_options(database_uri: str) -> dict:
    if database_uri.startswith("sqlite"):
        return {
            "connect_args": {
                "check_same_thread": False,
            }
        }
    return {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }

class Config:
    """基础配置类"""

    SQLITE_DATABASE_PATH = os.getenv(
        "SQLITE_DATABASE_PATH",
        os.path.join(BASE_DIR, "stock_cursor.sqlite3"),
    )
    SQLITE_DATABASE_URI = f"sqlite:///{SQLITE_DATABASE_PATH}"
    SQLALCHEMY_DATABASE_URI = SQLITE_DATABASE_URI
    SQLALCHEMY_ENGINE_OPTIONS = _build_sqlalchemy_engine_options(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask配置
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    # A 股印花税：卖方单边强制成本（2023-08-28 起 0.05%），
    # 多因子与单股回测共用同一默认值，调整口径只改这里
    DEFAULT_STAMP_DUTY_RATE = float(os.getenv('DEFAULT_STAMP_DUTY_RATE', '0.0005'))
    # 跨域与 SocketIO：生产环境应通过环境变量收紧 CORS_ORIGINS，
    # SOCKETIO_ASYNC_MODE=eventlet 时必须在入口先 monkey_patch
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')
    SOCKETIO_ASYNC_MODE = os.getenv('SOCKETIO_ASYNC_MODE', 'threading')

    # Redis配置
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    CELERY_BROKER_URL = os.getenv(
        'CELERY_BROKER_URL', f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    )
    CELERY_RESULT_BACKEND = os.getenv(
        'CELERY_RESULT_BACKEND', f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    )
    
    # 日志配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/stock_analysis.log')
    
    # 默认数据源：Parquet
    DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
    DATA_SOURCE = 'parquet'

    # 数据更新配置
    DATA_UPDATE_HOUR = int(os.getenv('DATA_UPDATE_HOUR', 18))  # 每日18点更新数据
    DATA_UPDATE_MINUTE = int(os.getenv('DATA_UPDATE_MINUTE', 0))
    
    # 预警配置
    EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER', 'smtp.qq.com')
    EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 587))
    EMAIL_USERNAME = os.getenv('EMAIL_USERNAME', '')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
    
    # 分页配置
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100
    
    # 大模型配置
    LLM_CONFIG = {
        'provider': os.getenv('LLM_PROVIDER', 'ollama'),  # 'ollama' | 'openai'
        'ollama': {
            'base_url': os.getenv('LLM_BASE_URL', 'http://localhost:11434'),
            'model': os.getenv('LLM_MODEL', 'qwen2.5-coder:latest'),
            'timeout': 60,
            'temperature': 0.1,
            'max_tokens': 2048
        },
        'openai': {
            'api_key': os.getenv('LLM_API_KEY'),
            'model': os.getenv('LLM_MODEL', 'gpt-3.5-turbo'),
            'base_url': os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1'),
            'timeout': 60,
            'temperature': 0.1,
            'max_tokens': 2048
        }
    }

    # AI 智能工作台：统一走 OpenAI 兼容 /v1/chat/completions 协议，
    # DeepSeek / 通义 / GLM / Kimi / OpenAI / 本地 Ollama 均可直接接入
    AI_ASSISTANT_CONFIG = {
        'api_key': os.getenv('LLM_API_KEY', ''),
        'base_url': os.getenv('LLM_BASE_URL', 'https://api.deepseek.com'),
        'model': os.getenv('LLM_MODEL', 'deepseek-chat'),
        'timeout': int(os.getenv('LLM_TIMEOUT', '120')),
        'temperature': float(os.getenv('LLM_TEMPERATURE', '0.3')),
        'max_tokens': int(os.getenv('LLM_MAX_TOKENS', '4096')),
        'max_tool_iterations': int(os.getenv('AI_MAX_TOOL_ITERATIONS', '10')),
    }

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    DATA_JOB_EXECUTION_MODE = os.getenv('DATA_JOB_EXECUTION_MODE', 'inline')

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    DATA_JOB_EXECUTION_MODE = os.getenv('DATA_JOB_EXECUTION_MODE', 'celery')

    @staticmethod
    def validate(app_config):
        """生产环境启动前强制校验，配置不完整时快速失败。"""
        secret = (app_config.get('SECRET_KEY') or '').strip()
        if not secret or secret in ('change-this-secret', 'dev', 'production'):
            raise RuntimeError(
                "生产环境必须设置真实的 SECRET_KEY（环境变量 SECRET_KEY），"
                "当前为空或仍为示例值"
            )


class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    DEBUG = True


# 配置字典
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
