import hashlib
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

def _stable_cache_key(args, kwargs) -> str:
    """参数摘要必须是跨进程稳定的：内置 hash() 受 PYTHONHASHSEED 随机化，
    多 worker/重启后同一请求会算出不同键，缓存永远 miss 且旧键变成垃圾。"""
    payload = repr(args) + repr(sorted(kwargs.items()))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

def cached(expire=3600, key_prefix='', cache_empty=False):
    """缓存装饰器。

    cache_empty=False（默认）时，函数返回 None/{}/[] 不写缓存：
    这些通常是数据缺失或失败路径的返回值，写入会让瞬时故障
    毒化缓存整整一个过期周期。
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{_stable_cache_key(args, kwargs)}"

            # 尝试从缓存获取
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return result

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            if not cache_empty and result in (None, {}, []):
                logger.debug(f"结果为空，跳过缓存: {cache_key}")
                return result
            cache.set(cache_key, result, expire)
            logger.debug(f"缓存设置: {cache_key}")

            return result
        return wrapper
    return decorator 