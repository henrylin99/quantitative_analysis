"""@cached 装饰器合约：键跨进程稳定，空结果/失败结果不写缓存。"""
import pytest

from app.utils import cache as cache_module
from app.utils.cache import CacheManager, cached


class _InMemoryCacheStub(CacheManager):
    """内存版 CacheManager 桩：绕过真实存储，记录写入行为。"""

    def __init__(self):
        super().__init__()
        self.store = {}
        self.set_keys = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, expire=3600):
        self.store[key] = value
        self.set_keys.append(key)
        return True

    def delete(self, key):
        self.store.pop(key, None)
        return True


@pytest.fixture()
def backend(monkeypatch):
    fake = _InMemoryCacheStub()
    monkeypatch.setattr(cache_module, "cache", fake)
    yield fake


def test_cache_key_is_stable_across_interpretations(backend):
    """同一参数必须生成同一键：内置 hash 受 PYTHONHASHSEED 随机化，
    多 worker 间会漂移成永远 miss。"""
    seen = []

    @cached(expire=60, key_prefix="t")
    def fn(a, b=None):
        seen.append(1)
        return {"v": len(seen)}

    first = fn(1, b=2)
    second = fn(1, b=2)

    assert first == second
    assert len(seen) == 1, "第二次应命中缓存"
    assert backend.set_keys, "结果应被写入缓存"


def test_different_args_produce_different_keys(backend):
    results = []

    @cached(expire=60, key_prefix="t")
    def fn(a):
        return {"a": a}

    results.append(fn(1))
    results.append(fn(2))

    assert results[0] != results[1]
    assert len(backend.store) == 2


def test_empty_results_are_not_cached(backend):
    calls = []

    @cached(expire=1800, key_prefix="t")
    def flaky():
        calls.append(1)
        return {}  # 模拟失败路径返回的空结果

    assert flaky() == {}
    assert flaky() == {}
    assert backend.set_keys == [], "空结果写入缓存会把瞬时故障毒化一个过期周期"
    assert len(calls) == 2, "空结果不缓存，每次都重查数据源"


def test_none_result_is_not_cached(backend):
    @cached(expire=600, key_prefix="t")
    def fn():
        return None

    fn()
    assert backend.set_keys == []
