"""fund_service 合约测试：聚合、时间戳归一、窗口钳制、缓存（fake 客户端注入）。"""

import pytest

from app.services.fund_service import (
    FUND_WINDOW_MAX_DAYS,
    FundService,
    ymd_to_ms,
)


class FakeFundClient:
    """记录调用并回放固定数据的最小客户端。"""

    def __init__(self):
        self.calls = []

    def fund_profile(self, thscode):
        self.calls.append(("fund_profile", thscode))
        return [
            {
                "thscode": thscode,
                "fund_name": "沪深300ETF",
                "estab_date": 1751385600000,  # 北京时间 2025-07-02 零点
            }
        ]

    def fund_market_snapshot(self, thscode):
        self.calls.append(("fund_market_snapshot", thscode))
        return [{"thscode": thscode, "last_price": 4.01}]

    def fund_historical(self, thscode, start_ms, end_ms, interval="1d"):
        self.calls.append(("fund_historical", thscode, start_ms, end_ms))
        return [
            {"date_ms": end_ms - 86400000, "close": 3.99},
            {"date_ms": end_ms, "close": 4.01},
        ]

    def fund_nav(self, thscode):
        self.calls.append(("fund_nav", thscode))
        return [{"nav_date": 1751385600000, "unit_nav": 1.05}]

    def fund_returns(self, thscode):
        self.calls.append(("fund_returns", thscode))
        return {"item": [{"return_year": 12.5, "rank_year": 3, "rank_total_year": 100}]}

    def fund_drawdowns(self, thscode):
        self.calls.append(("fund_drawdowns", thscode))
        return {"item": [{"year": -8.1, "now": -15.0}]}

    def fund_holdings(self, thscode):
        self.calls.append(("fund_holdings", thscode))
        return {
            "total_stock_ratio_pct": 92.1,
            "timestamp": 1751385600000,
            "item": [
                {
                    "thscode": "600519.SH",
                    "stock_name": "贵州茅台",
                    "hold_ratio": 9.8,
                    "publish_date_ms": 1751385600000,
                }
            ],
        }

    def fund_holders_detail(self, thscode, merge_scope="all"):
        self.calls.append(("fund_holders_detail", thscode))
        return [{"ins_position": 55.0, "report_date_ms": 1751385600000}]

    def fund_holders_top(self, thscode, limit=10):
        self.calls.append(("fund_holders_top", thscode))
        return [{"holder_name": "中央汇金", "hold_rate_pct": 1.2}]

    def fund_dividends(self, thscode):
        self.calls.append(("fund_dividends", thscode))
        return {
            "dividend_count": 1,
            "dividend_total": 0.15,
            "item": [{"ex_dividend_date_ms": 1751385600000}],
        }


@pytest.fixture
def service():
    return FundService(client=FakeFundClient())


# ---- 时间口径 ----

def test_ymd_to_ms_is_beijing_midnight():
    # 2025-07-02 北京时间零点 = 2025-07-01 16:00 UTC（与客户端合约测试同口径）
    assert ymd_to_ms("20250702") == 1751385600000


def test_ymd_to_ms_rejects_bad_format():
    with pytest.raises(ValueError):
        ymd_to_ms("2025-07-02")


# ---- T1：资料 / 快照 / 历史 / 业绩 / 持仓 ----

def test_get_profile_converts_estab_date(service):
    profile = service.get_profile("510300.SH")
    assert profile["fund_name"] == "沪深300ETF"
    assert profile["estab_date_ymd"] == "20250702"


def test_get_history_converts_dates_and_orders(service):
    result = service.get_history("510300.SH", "20250601", "20250702")
    dates = [row["date"] for row in result["items"]]
    assert dates[-1] == "20250702"
    assert result["items"][-1]["close"] == 4.01


def test_get_history_clamps_overlong_window(service):
    service.get_history("510300.SH", "20000101", "20250702")
    _, _, start_ms, _ = service.client.calls[-1]
    end_ms = ymd_to_ms("20250702")
    assert end_ms - start_ms <= FUND_WINDOW_MAX_DAYS * 86400 * 1000


def test_get_history_rejects_reversed_window(service):
    with pytest.raises(ValueError):
        service.get_history("510300.SH", "20250702", "20250601")


def test_get_performance_aggregates(service):
    payload = service.get_performance("510300.SH")
    assert payload["nav_latest"]["nav_date_ymd"] == "20250702"
    assert payload["returns"]["return_year"] == 12.5
    assert payload["drawdowns"]["now"] == -15.0


def test_get_holdings_splits_summary_and_items(service):
    payload = service.get_holdings("025480.OF")
    assert payload["summary"]["total_stock_ratio_pct"] == 92.1
    item = payload["items"][0]
    assert item["thscode"] == "600519.SH"
    assert item["publish_date_ms_ymd"] == "20250702"


# ---- T2 ----

def test_get_holders_merges_structure_and_top(service):
    payload = service.get_holders("510300.SH")
    assert payload["structure"][0]["ins_position"] == 55.0
    assert payload["top"][0]["holder_name"] == "中央汇金"


def test_get_dividends_converts_dates(service):
    payload = service.get_dividends("510300.SH")
    assert payload["items"][0]["ex_dividend_date_ms_ymd"] == "20250702"


# ---- 缓存 ----

def test_caching_avoids_repeat_calls(service):
    service.get_profile("510300.SH")
    service.get_profile("510300.SH")
    assert service.client.calls.count(("fund_profile", "510300.SH")) == 1


def test_different_codes_cached_separately(service):
    service.get_profile("510300.SH")
    service.get_profile("025480.OF")
    assert len([c for c in service.client.calls if c[0] == "fund_profile"]) == 2


# ---- 净值序列（图表用） ----

def test_get_nav_series_converts_dates(service):
    service.client.fund_nav = lambda thscode, range=None, nav_type="unit,adj": [
        {"nav_date": 1751385600000, "unit_nav": 1.05}
    ]
    rows = service.get_nav_series("025480.OF", range="year")
    assert rows[0]["nav_date_ymd"] == "20250702"
    assert rows[0]["unit_nav"] == 1.05


def test_get_holders_filters_top_to_latest_report_date(service):
    service.client.fund_holders_top = lambda thscode, limit=10: [
        {"holder_name": "旧期持有人", "hold_rate_pct": 1.0, "report_date_ms": 1700000000000},
        {"holder_name": "汇金A", "hold_rate_pct": 42.8, "report_date_ms": 1751385600000},
        {"holder_name": "汇金B", "hold_rate_pct": 5.0, "report_date_ms": 1751385600000},
    ]
    payload = service.get_holders("510300.SH")
    names = [row["holder_name"] for row in payload["top"]]
    assert names == ["汇金A", "汇金B"]


# ---- 基金检索（列表页） ----

def test_search_funds_keeps_only_fund_rows(service):
    service.client.ticker_search = lambda query, asset_type=None, limit=10: [
        {"thscode": "510300.SH", "name": "沪深300ETF", "asset_type": "fund-etf"},
        {"thscode": "881273.TI", "name": "白酒", "asset_type": "a-share-index"},
        {"thscode": "025480.OF", "name": "沪深300A", "asset_type": "fund-otc"},
    ]
    rows = service.search_funds("沪深300")
    assert [row["thscode"] for row in rows] == ["510300.SH", "025480.OF"]
