from flask_sqlalchemy import SQLAlchemy
import redis
from config import Config
from flask_migrate import Migrate
from flask_socketio import SocketIO

# 数据库实例
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')

# Redis实例
redis_client = redis.Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB,
    decode_responses=True
) 