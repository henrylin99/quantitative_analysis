import hashlib
import json
import threading
import time
from functools import wraps

from loguru import logger


class CacheManager:
    """进程内 TTL 缓存。

    原 Redis 实现已随去 Redis 化移除。与原实现的行为差异：
    进程重启后缓存清空；多进程部署时各进程缓存互不共享。
    存取均经 JSON 序列化，保证每次返回独立副本，调用方修改
    返回值不会污染缓存。
    """

    # 兜底上限：键随参数组合增长（如逐股票逐日期），长期运行进程
    # 需要防止无界膨胀。超过后先清已过期键，仍超则按写入顺序淘汰。
    DEFAULT_MAX_ENTRIES = 4096

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._store = {}  # key -> (expire_at_monotonic, json_str)
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get(self, key):
        """获取缓存，命中返回独立副本，过期/缺失/损坏返回 None。"""
        try:
            with self._lock:
                entry = self._store.get(key)
                if entry is None:
                    return None
                expire_at, data = entry
                if time.monotonic() > expire_at:
                    del self._store[key]
                    return None
            return json.loads(data)
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {e}")
            # 解析失败说明存储损坏，删除避免反复报错
            self.delete(key)
            return None

    def set(self, key, value, expire=3600):
        """设置缓存（expire 单位秒），失败返回 False 不抛出。"""
        try:
            data = json.dumps(value, ensure_ascii=False, default=str)
            expire_at = time.monotonic() + max(int(expire), 1)
            with self._lock:
                self._evict_if_over_capacity()
                self._store[key] = (expire_at, data)
            return True
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, 错误: {e}")
            return False

    def delete(self, key):
        """删除缓存。"""
        with self._lock:
            self._store.pop(key, None)
        return True

    def exists(self, key):
        """检查缓存是否存在且未过期（只查表，不做 JSON 反序列化）。"""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            if time.monotonic() > entry[0]:
                del self._store[key]
                return False
            return True

    def _evict_if_over_capacity(self):
        """须在持有锁时调用。先清过期键，仍超限则按写入顺序淘汰一批。"""
        if len(self._store) < self._max_entries:
            return
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._store.items() if exp <= now]:
            del self._store[key]
        if len(self._store) >= self._max_entries:
            for key in list(self._store)[: self._max_entries // 10]:
                del self._store[key]

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
