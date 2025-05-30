import json
from functools import wraps
from app.extensions import redis_client
from loguru import logger

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, redis_client=redis_client):
        self.redis = redis_client
    
    def get(self, key):
        """获取缓存"""
        try:
            data = self.redis.get(key)
            if data:
                # 处理不同类型的数据
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                elif isinstance(data, str):
                    # 数据已经是字符串，直接使用
                    pass
                else:
                    # 其他类型转换为字符串
                    data = str(data)
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {e}")
            # 如果解析失败，删除损坏的缓存
            try:
                self.redis.delete(key)
            except:
                pass
            return None
    
    def set(self, key, value, expire=3600):
        """设置缓存"""
        try:
            data = json.dumps(value, ensure_ascii=False, default=str)
            self.redis.setex(key, expire, data.encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, 错误: {e}")
            return False
    
    def delete(self, key):
        """删除缓存"""
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, 错误: {e}")
            return False
    
    def exists(self, key):
        """检查缓存是否存在"""
        try:
            return self.redis.exists(key)
        except Exception as e:
            logger.error(f"检查缓存失败: {key}, 错误: {e}")
            return False

# 全局缓存实例
cache = CacheManager()

def cached(expire=3600, key_prefix=''):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存获取
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.set(cache_key, result, expire)
            logger.debug(f"缓存设置: {cache_key}")
            
            return result
        return wrapper
    return decorator 