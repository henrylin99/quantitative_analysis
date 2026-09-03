"""CacheManager 合约：exists 只查表不反序列化；过期键读取即清除。"""
import time

from app.utils.cache import CacheManager


def test_exists_false_for_missing_key():
    cache = CacheManager()
    assert cache.exists("missing") is False


def test_exists_true_for_live_key():
    cache = CacheManager()
    cache.set("k", {"a": 1})
    assert cache.exists("k") is True


def test_exists_does_not_deserialize_value():
    """损坏的 JSON 值：exists 应判在（只查表），get 才负责清理损坏条目。"""
    cache = CacheManager()
    cache._store["broken"] = (time.monotonic() + 60, "not-json")
    assert cache.exists("broken") is True


def test_exists_false_and_purges_expired_key():
    cache = CacheManager()
    cache._store["stale"] = (time.monotonic() - 1, '"x"')
    assert cache.exists("stale") is False
    assert "stale" not in cache._store
