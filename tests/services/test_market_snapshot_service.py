"""市场看板聚合与服务层合约测试（fake client，不发网络请求）。"""

import pandas as pd
import pytest

from app.services import market_snapshot_service as svc_mod
from app.services.market_dashboard import build_dashboard_payload, limit_ratio_for
from app.services.market_snapshot_service import MarketSnapshotService

pytestmark = pytest.mark.module_data_jobs


def _row(ts_code, price, pct, prev, amount_yuan, name=None):
    return {"ts_code": ts_code, "name": name, "price": price, "pct_chg": pct,
            "prev_close": prev, "amount_yuan": amount_yuan}


def _frame(rows):
    return pd.DataFrame(rows)


# ---- 聚合 ----

def test_dashboard_breadth_distribution_and_boards():
    rows = [
        _row("000001.SZ", 11.0, 3.0, 10.677, 2e9, "甲"),
        _row("000002.SZ", 5.0, -3.0, 5.1, 1e9, "乙"),
        _row("300001.SZ", 10.0, 20.05, 8.33, 5e8, "丙"),   # 创业板 20% 涨停近似
        _row("600000.SH", 9.0, 0.0, 9.0, 3e8, "丁"),
        _row("600001.SH", 8.0, -10.5, 8.94, 2e8, "戊"),    # 主板跌停近似
    ]
    payload = build_dashboard_payload(_frame(rows))

    breadth = payload["breadth"]
    assert breadth["up"] == 2 and breadth["down"] == 2 and breadth["flat"] == 1
    assert breadth["limit_up"] == 1 and breadth["limit_down"] == 1
    assert payload["total_amount_yuan"] == pytest.approx(4.0e9)

    dist = {item["bucket"]: item["count"] for item in payload["distribution"]}
    assert dist["0 ~ 2%"] == 1
    assert dist["2% ~ 5%"] == 1
    assert dist["-5% ~ -2%"] == 1
    assert dist["< -5%"] == 1
    assert dist[">= 5%"] == 1

    assert payload["top_gainers"][0]["ts_code"] == "300001.SZ"
    assert payload["top_losers"][0]["ts_code"] == "600001.SH"
    assert payload["top_amount"][0]["ts_code"] == "000001.SZ"


def test_dashboard_empty_frame():
    payload = build_dashboard_payload(pd.DataFrame())
    assert payload["breadth"] == {}
    assert payload["top_gainers"] == []


def test_limit_ratio_by_board():
    assert limit_ratio_for("830001.BJ") == 0.30
    assert limit_ratio_for("300001.SZ") == 0.20
    assert limit_ratio_for("688001.SH") == 0.20
    assert limit_ratio_for("600000.SH") == 0.10


# ---- 服务：快照缓存与降级 ----

class _FakeFuyaoClient:
    def __init__(self, snapshot_items=None, fail=False, empty=False):
        self.snapshot_items = snapshot_items or []
        self.fail = fail
        self.empty = empty
        self.snapshot_calls = 0

    def snapshot_page(self, limit=None, offset=0, thscodes=None):
        self.snapshot_calls += 1
        if self.fail:
            raise svc_mod.FuyaoError(4001, "限频")
        if thscodes:
            wanted = set(thscodes)
            items = [item for item in self.snapshot_items if item["thscode"] in wanted]
            return {"item": items}
        if self.empty:
            return {"item": []}
        return {"item": self.snapshot_items}

    def snapshot_all(self, max_pages=50):
        self.snapshot_calls += 1
        if self.fail:
            raise svc_mod.FuyaoError("network", "挂了")
        if self.empty:
            return [], None
        return self.snapshot_items, 123


def _snapshot_item(ts_code, price, pct):
    return {"thscode": ts_code, "last_price": price, "price_change_ratio_pct": pct,
            "open_price": price, "high_price": price, "low_price": price,
            "prev_price": price / (1 + pct / 100), "price_change": price * pct / 100,
            "volume": 1000, "turnover": price * 1000}


def test_get_quotes_fetches_and_caches(monkeypatch):
    client = _FakeFuyaoClient([_snapshot_item("600000.SH", 9.28, 1.2)])
    service = MarketSnapshotService(client=client)

    quotes = service.get_quotes(["600000.SH", "000001.SZ"])
    assert "600000.SH" in quotes
    assert quotes["600000.SH"]["pct_chg"] == pytest.approx(1.2)

    # 第二次命中缓存，不再发请求
    service.get_quotes(["600000.SH"])
    assert client.snapshot_calls == 1


def test_get_quotes_falls_back_to_stale_cache_on_failure(monkeypatch):
    client = _FakeFuyaoClient([_snapshot_item("600000.SH", 9.28, 1.2)])
    service = MarketSnapshotService(client=client)
    service.get_quotes(["600000.SH"])

    client.fail = True
    quotes = service.get_quotes(["600000.SH"])
    assert quotes["600000.SH"]["last_price"] == pytest.approx(9.28)


def test_dashboard_degrades_to_local_parquet(monkeypatch, tmp_path):
    """扶摇失败时回退本地日线最近分区，并标记 degraded。"""
    client = _FakeFuyaoClient(fail=True)
    service = MarketSnapshotService(client=client)

    local = pd.DataFrame([
        {"ts_code": "000001.SZ", "close": 11.0, "pct_chg": 2.0, "pre_close": 10.78, "amount": 1e6},
        {"ts_code": "600000.SH", "close": 9.0, "pct_chg": -1.0, "pre_close": 9.09, "amount": 2e6},
    ])
    import app.utils.parquet_job_helpers as helpers_mod
    monkeypatch.setattr(helpers_mod, "latest_partition_date", lambda *a, **k: "20260904")

    class _FakeReader:
        def get_daily(self, **kwargs):
            return local

    import app.services.data_reader as reader_mod
    monkeypatch.setattr(reader_mod, "ParquetDataReader", _FakeReader)

    payload = service.get_dashboard()

    assert payload["degraded"] is True
    assert payload["source"] == "local_parquet"
    assert payload["as_of"] == "20260904"
    assert payload["breadth"]["up"] == 1
    assert "degraded_reason" in payload


# ---- 数据源状态 ----

def test_source_status_reports_configuration(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "tok")
    monkeypatch.setenv("FUYAO_API_KEY", "sk-ok")
    monkeypatch.setenv("TICKFLOW_API_KEY", "")

    client = _FakeFuyaoClient([_snapshot_item("600000.SH", 9.28, 1.2)])
    service = MarketSnapshotService(client=client)

    class _FakeTickflow:
        def __init__(self, api_key=None):
            pass

        def detect_tier(self):
            return "none"

    import app.utils.data_sources.tickflow_client as tf_mod
    monkeypatch.setattr(tf_mod, "TickflowClient", _FakeTickflow)

    status = service.get_source_status(force=True)
    assert status["tushare"]["configured"] is True
    assert status["fuyao"]["configured"] is True and status["fuyao"]["ok"] is True
    assert status["tickflow"]["configured"] is False
    assert status["tickflow"]["tier"] == "none"


def test_source_status_cached(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "tok")
    monkeypatch.setenv("FUYAO_API_KEY", "sk-ok")
    monkeypatch.delenv("TICKFLOW_API_KEY", raising=False)

    client = _FakeFuyaoClient([_snapshot_item("600000.SH", 9.28, 1.2)])
    service = MarketSnapshotService(client=client)
    service.get_source_status(force=True)
    service.get_source_status()
    assert client.snapshot_calls == 1
