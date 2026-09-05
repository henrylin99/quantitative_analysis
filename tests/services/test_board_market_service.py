"""board_market_service 契约测试（fake 客户端注入，不发真实请求）。"""

import time

import pytest

from app.services import board_market_service as bms
from app.utils.data_sources.fuyao_client import FuyaoError

pytestmark = pytest.mark.module_data_jobs


def _pool_row(thscode="605577.SH", cnt=5):
    return {
        "thscode": thscode,
        "ticker": thscode.split(".")[0],
        "name": "龙版传媒",
        "is_st": False,
        "is_new": False,
        "last_price": 15.55,
        "price_change_ratio_pct": 9.9717,
        "limit_up_time": "09:31",
        "limit_up_reason": "AI漫剧+出版发行",
        "continue_day_text": f"{cnt}连板",
        "continue_day_cnt": cnt,
        "seal_money": 83333989,
        "max_seal_money": 167993942.95,
    }


class _FakeClient:
    def __init__(self):
        self.trading_days_value = [{"date_ms": 0, "date": "20260904"}]
        self.pool_data = {
            "pagination": {"total": 1, "pages": 1, "size": 100, "page": 1},
            "item": [_pool_row()],
        }
        self.ladder_data = {
            "item": [
                {
                    "date": "2026-09-04",
                    "boards": {
                        "two_board": [{"thscode": "600108.SH"}] * 6,
                        "five_board": [{"thscode": "605577.SH"}],
                    },
                }
            ]
        }
        self.catalog_data = [
            {"thscode": "881101.TI", "name": "种植业与林业"},
            {"thscode": "884001.TI", "name": "种子生产"},
        ]
        self.snapshot_rows = [
            {
                "thscode": "881101.TI",
                "last_price": 4890.6,
                "price_change_ratio_pct": 2.476,
                "turnover": 17778347000,
                "volume": 2296708100,
            }
        ]
        self.constituents = [
            {"thscode": "000998.SZ", "ticker": "000998", "name": "隆平高科"}
        ]
        self.calls = []

    def trading_days(self):
        self.calls.append("trading_days")
        return self.trading_days_value

    def limit_up_pool(self, date_ms=None, page=1, size=100, **_):
        self.calls.append(("pool", date_ms, page, size))
        return self.pool_data

    def limit_up_ladder(self):
        self.calls.append("ladder")
        return self.ladder_data

    def ths_index_catalog(self, tag=None):
        self.calls.append(("catalog", tag))
        return self.catalog_data

    def index_snapshot(self, thscodes):
        self.calls.append(("snapshot", list(thscodes)))
        return [r for r in self.snapshot_rows if r["thscode"] in thscodes], None

    def ths_index_constituents(self, thscode):
        self.calls.append(("constituents", thscode))
        return self.constituents


@pytest.fixture()
def service(monkeypatch):
    svc = bms.BoardMarketService(client=_FakeClient())
    monkeypatch.setattr(bms, "get_board_market_service", lambda: svc)
    return svc


def test_pool_normalizes_fields_and_resolves_latest_date(service):
    payload = service.get_limit_up_pool()
    row = payload["items"][0]
    assert payload["date"] == "20260904"
    assert row["ts_code"] == "605577.SH"
    assert row["pct_chg"] == pytest.approx(9.9717)
    assert row["continue_day_text"] == "5连板"
    assert row["seal_money"] == 83333989
    # date_ms 为北京时间零点
    (_, date_ms, _, _), = [c for c in service.client.calls if isinstance(c, tuple) and c[0] == "pool"]
    assert date_ms == 1788451200000


def test_pool_rejects_bad_date(service):
    with pytest.raises(ValueError):
        service.get_limit_up_pool(date="2026/09/04")


def test_pool_serves_stale_on_error(service, monkeypatch):
    service.get_limit_up_pool(date="20260901")

    def _boom(**_):
        raise FuyaoError("network", "down")

    service.client.limit_up_pool = _boom
    # 历史日新鲜期 24h，跳到 24h+30min：新鲜判定失效但仍在 1h 回供窗口内
    real_monotonic = time.monotonic()
    monkeypatch.setattr(bms.time, "monotonic", lambda: real_monotonic + 24 * 3600 + 1800)
    payload = service.get_limit_up_pool(date="20260901")
    assert payload["stale"] is True
    assert payload["items"][0]["ts_code"] == "605577.SH"


def test_ladder_counts_and_highest(service):
    payload = service.get_limit_up_ladder()
    day = payload["days"][0]
    assert day["counts"] == {"2": 6, "3": 0, "4": 0, "5": 1, "6": 0, "7": 0}
    assert day["highest"] == 5
    assert day["total"] == 7


def test_boards_joins_catalog_and_snapshot_sorted_desc(service):
    payload = service.get_boards("industry")
    assert payload["tag"] == "industry"
    assert payload["items"][0]["thscode"] == "881101.TI"
    assert payload["items"][0]["name"] == "种植业与林业"
    assert payload["items"][0]["pct_chg"] == pytest.approx(2.476)
    assert payload["unavailable"] == ["884001.TI"]


def test_boards_rejects_bad_tag(service):
    with pytest.raises(ValueError):
        service.get_boards("sector")


def test_constituents_enriched_from_quote_frame(service, monkeypatch):
    def _fake_quote_index():
        return {
            "000998.SZ": {
                "name": "隆平高科",
                "last_price": 13.5,
                "pct_chg": 1.23,
                "amount_yuan": 8.6e8,
            }
        }

    monkeypatch.setattr(service, "_quote_frame_index", _fake_quote_index, raising=False)
    payload = service.get_board_constituents("884001.TI")
    row = payload["items"][0]
    assert payload["code"] == "884001.TI"
    assert row["name"] == "隆平高科"
    assert row["last_price"] == 13.5
    assert row["pct_chg"] == pytest.approx(1.23)


def test_fallback_trade_date_skips_weekend():
    # 纯函数：周末向前回退到周五
    assert len(bms.BoardMarketService._fallback_trade_date()) == 8
