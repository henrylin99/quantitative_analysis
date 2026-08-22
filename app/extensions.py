from flask_sqlalchemy import SQLAlchemy
import os
import redis
from config import Config
from flask_migrate import Migrate
from flask_socketio import SocketIO

# 数据库实例
db = SQLAlchemy()
migrate = Migrate()
# eventlet 模式必须在应用入口最先 monkey_patch，否则所有阻塞调用会卡死
# 事件循环；默认 threading 模式无需补丁，本地开发更稳
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode=os.getenv('SOCKETIO_ASYNC_MODE', 'threading'),
)

# Redis实例（惰性连接：构造不建立连接，首次命令才连接）
redis_client = redis.Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
)