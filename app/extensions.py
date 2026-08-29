from flask_sqlalchemy import SQLAlchemy
import os
import sqlite3
import redis
from config import Config
from flask_migrate import Migrate
from flask_socketio import SocketIO
from sqlalchemy import event
from sqlalchemy.engine import Engine


# SQLite 并发防护：web 与 celery worker 共写同一库文件。WAL 允许读写并行，
# synchronous=NORMAL 是 WAL 的推荐搭配；busy_timeout 由 config.py 的
# connect_args timeout 提供，两层配合避免 database is locked
@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()

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