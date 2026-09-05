"""StockNameRegistry 契约测试（临时缓存目录 + fake tickflow 客户端）。"""

import pytest

from app.services.stock_name_registry import StockNameRegistry

pytestmark = pytest.mark.module_data_jobs


class _FakeTickflow:
    def __init__(self, per_exchange):
        self.per_exchange = per_exchange
        self.exchanges_called = []

    def instruments(self, exchange="SH", instrument_type="stock", limit=5000):
        self.exchanges_called.append(exchange)
        return self.per_exchange.get(exchange, [])


@pytest.fixture()
def registry(tmp_path):
    return StockNameRegistry(cache_path=tmp_path / "instruments.parquet")


def test_fetch_names_merges_three_exchanges(monkeypatch):
    fake = _FakeTickflow(
        {
            "SH": [{"symbol": "600000.SH", "name": "浦发银行"}],
            "SZ": [{"symbol": "000001.SZ", "name": "平安银行"}],
            "BJ": [{"symbol": "430047.BJ", "name": "诺思兰德"}],
        }
    )
    monkeypatch.setattr(
        "app.utils.data_sources.tickflow_client.TickflowClient", lambda: fake
    )
    from app.services.stock_name_registry import fetch_tickflow_names

    names = fetch_tickflow_names()
    assert names["600000.SH"] == "浦发银行"
    assert names["430047.BJ"] == "诺思兰德"
    assert set(fake.exchanges_called) == {"SH", "SZ", "BJ"}


def test_name_map_merges_tickflow_and_stock_basic(registry, monkeypatch):
    fake = _FakeTickflow(
        {
            "SH": [{"symbol": "600000.SH", "name": "浦发银行"},
                   {"symbol": "603999.SH", "name": "新股示例"}],
        }
    )
    monkeypatch.setattr(
        "app.services.stock_name_registry.fetch_tickflow_names", lambda client=None: {"600000.SH": "浦发银行", "603999.SH": "新股示例"}
    )
    monkeypatch.setattr(
        "app.services.data_reader.ParquetDataReader.get_stock_basic",
        lambda self: __import__("pandas").DataFrame(
            {"ts_code": ["600000.SH"], "name": ["浦发银行(本地)"]}
        ),
    )
    name_map = registry.name_map()
    # stock_basic 优先，TickFlow 补缺
    assert name_map["600000.SH"] == "浦发银行(本地)"
    assert name_map["603999.SH"] == "新股示例"


def test_merge_names_fills_missing_only(registry, monkeypatch):
    monkeypatch.setattr(
        registry, "name_map", lambda max_age_seconds=None: {"600000.SH": "浦发银行"}
    )
    rows = [
        {"ts_code": "600000.SH", "name": None},
        {"ts_code": "000001.SZ", "name": "已有名称"},
    ]
    merged = registry.merge_names(rows)
    assert merged[0]["name"] == "浦发银行"
    assert merged[1]["name"] == "已有名称"


def test_cache_roundtrip(registry, monkeypatch):
    calls = {"n": 0}

    def _fetch(client=None):
        calls["n"] += 1
        return {"600000.SH": "浦发银行"}

    monkeypatch.setattr(
        "app.services.stock_name_registry.fetch_tickflow_names", _fetch
    )
    monkeypatch.setattr(
        "app.services.data_reader.ParquetDataReader.get_stock_basic",
        lambda self: __import__("pandas").DataFrame(),
    )
    registry.name_map()
    registry.invalidate()
    registry.name_map()
    # 第二次走 parquet 落盘缓存，不再触发网络
    assert calls["n"] == 1
    assert registry._cache_path.exists()
