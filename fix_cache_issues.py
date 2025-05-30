#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复缓存问题的脚本
解决Redis缓存解码错误和相关问题
"""

import redis
from app import create_app
from app.extensions import db
from loguru import logger

def fix_cache_issues():
    """修复缓存问题"""
    print("🔧 修复缓存问题...")
    print("=" * 50)
    
    try:
        # 创建应用上下文
        app = create_app()
        
        with app.app_context():
            # 1. 清理Redis缓存
            try:
                # 尝试连接Redis
                redis_client = redis.Redis(
                    host=app.config.get('REDIS_HOST', 'localhost'),
                    port=app.config.get('REDIS_PORT', 6379),
                    db=app.config.get('REDIS_DB', 0),
                    decode_responses=True
                )
                
                # 测试连接
                redis_client.ping()
                
                # 清理所有缓存
                keys = redis_client.keys('*')
                if keys:
                    redis_client.delete(*keys)
                    print(f"✅ 清理了 {len(keys)} 个缓存键")
                else:
                    print("✅ 缓存已经是空的")
                    
            except redis.ConnectionError:
                print("⚠️  Redis未运行，跳过缓存清理")
            except Exception as e:
                print(f"⚠️  清理缓存时出错: {e}")
            
            # 2. 修复缓存工具类
            cache_utils_content = '''import redis
import pickle
import json
import hashlib
from functools import wraps
from typing import Any, Optional
from loguru import logger

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.default_expire = 3600  # 默认1小时过期
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if not self.redis_client:
            return None
            
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            # 尝试JSON解码
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # 如果JSON解码失败，尝试pickle
                try:
                    if isinstance(value, str):
                        value = value.encode('utf-8')
                    return pickle.loads(value)
                except (pickle.PickleError, TypeError):
                    # 如果都失败，返回原始字符串
                    return value
                    
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {e}")
            return None
    
    def set(self, key: str, value: Any, expire: int = None) -> bool:
        """设置缓存"""
        if not self.redis_client:
            return False
            
        try:
            expire = expire or self.default_expire
            
            # 优先使用JSON序列化
            try:
                serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                # JSON序列化失败，使用pickle
                serialized_value = pickle.dumps(value)
            
            return self.redis_client.setex(key, expire, serialized_value)
            
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, 错误: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        if not self.redis_client:
            return False
            
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, 错误: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """清理匹配模式的缓存"""
        if not self.redis_client:
            return 0
            
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"清理缓存失败: {pattern}, 错误: {e}")
            return 0

def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    key_parts = [prefix]
    
    # 添加位置参数
    for arg in args:
        key_parts.append(str(arg))
    
    # 添加关键字参数
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")
    
    key_string = ":".join(key_parts)
    
    # 如果键太长，使用哈希
    if len(key_string) > 200:
        return f"{prefix}:{hashlib.md5(key_string.encode()).hexdigest()}"
    
    return key_string

def cached(expire: int = 3600, key_prefix: str = "default"):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = generate_cache_key(key_prefix, func.__name__, *args, **kwargs)
            
            # 尝试从缓存获取
            try:
                from app.extensions import cache_manager
                if cache_manager:
                    cached_result = cache_manager.get(cache_key)
                    if cached_result is not None:
                        return cached_result
            except Exception as e:
                logger.warning(f"缓存获取失败: {e}")
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 保存到缓存
            try:
                from app.extensions import cache_manager
                if cache_manager and result is not None:
                    cache_manager.set(cache_key, result, expire)
            except Exception as e:
                logger.warning(f"缓存保存失败: {e}")
            
            return result
        return wrapper
    return decorator
'''
            
            # 保存修复的缓存工具
            with open('app/utils/cache_fixed.py', 'w', encoding='utf-8') as f:
                f.write(cache_utils_content)
            
            print("✅ 创建了修复的缓存工具类")
            
            # 3. 更新扩展配置
            extensions_content = '''from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import redis
from app.utils.cache_fixed import CacheManager

# 数据库
db = SQLAlchemy()
migrate = Migrate()

# 缓存管理器
cache_manager = None

def init_extensions(app):
    """初始化扩展"""
    global cache_manager
    
    # 初始化数据库
    db.init_app(app)
    migrate.init_app(app, db)
    
    # 初始化缓存
    try:
        redis_client = redis.Redis(
            host=app.config.get('REDIS_HOST', 'localhost'),
            port=app.config.get('REDIS_PORT', 6379),
            db=app.config.get('REDIS_DB', 0),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        # 测试连接
        redis_client.ping()
        cache_manager = CacheManager(redis_client)
        app.logger.info("Redis缓存初始化成功")
        
    except Exception as e:
        app.logger.warning(f"Redis缓存初始化失败: {e}")
        cache_manager = CacheManager()  # 无缓存模式
'''
            
            with open('app/extensions_fixed.py', 'w', encoding='utf-8') as f:
                f.write(extensions_content)
            
            print("✅ 创建了修复的扩展配置")
            
            print("\n📋 修复完成！")
            print("💡 建议:")
            print("   1. 将 app/extensions_fixed.py 替换 app/extensions.py")
            print("   2. 更新导入语句使用新的缓存工具")
            print("   3. 重启应用以应用修复")
            
            return True
            
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        return False

if __name__ == "__main__":
    fix_cache_issues() 