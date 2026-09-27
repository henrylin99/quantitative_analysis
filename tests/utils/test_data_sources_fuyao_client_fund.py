"""扶摇基金接口客户端合约测试：路径、参数、信封解包。"""

import pytest

from app.utils.data_sources.fuyao_client import FuyaoClient, FuyaoError


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """记录每次调用的 url/params，按序回放响应。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None, stream=False, **kwargs):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(payload={"code": 0, "message": "ok", "data": {}})


def _client_with(responses=None) -> tuple:
    session = FakeSession(responses)
    client = FuyaoClient(api_key="sk-test", throttle_seconds=0, session=session)
    return client, session


def _envelope(data):
    return FakeResponse(payload={"code": 0, "message": "ok", "data": data})


# ---- T1：行情 / 业绩 / 持仓 / 资料 ----

def test_fund_profile_hits_profile_detail():
    client, session = _client_with(
        [_envelope({"item": [{"thscode": "025480.OF", "fund_name": "测试基金"}]})]
    )
    rows = client.fund_profile("025480.OF")
    assert rows[0]["fund_name"] == "测试基金"
    call = session.calls[0]
    assert call["url"].endswith("/api/fund/profile/detail")
    assert call["params"]["thscode"] == "025480.OF"
    assert call["headers"]["X-api-key"] == "sk-test"


def test_fund_market_snapshot_single_code():
    client, session = _client_with([_envelope({"item": [{"thscode": "510300.SH"}]})])
    rows = client.fund_market_snapshot("510300.SH")
    assert rows[0]["thscode"] == "510300.SH"
    assert session.calls[0]["url"].endswith("/api/fund/market/snapshot")


def test_fund_historical_sends_window_ms():
    client, session = _client_with([_envelope({"item": [{"date_ms": 1751385600000}]})])
    items = client.fund_historical("510300.SH", start_ms=1704038400000, end_ms=1751385600000)
    assert items[0]["date_ms"] == 1751385600000
    params = session.calls[0]["params"]
    assert params == {
        "thscode": "510300.SH",
        "interval": "1d",
        "start": 1704038400000,
        "end": 1751385600000,
    }


def test_fund_nav_default_nav_type():
    client, session = _client_with([_envelope({"item": [{"unit_nav": 1.23}]})])
    assert client.fund_nav("510300.SH")[0]["unit_nav"] == 1.23
    params = session.calls[0]["params"]
    assert params["nav_type"] == "unit,adj"
    assert "range" not in params  # 可空参数不发送


def test_fund_returns_and_drawdowns_return_whole_data():
    client, session = _client_with(
        [_envelope({"item": [{"return_year": 12.5}]}), _envelope({"item": [{"year": -8.1}]})]
    )
    assert client.fund_returns("510300.SH")["item"][0]["return_year"] == 12.5
    assert client.fund_drawdowns("510300.SH")["item"][0]["year"] == -8.1
    assert session.calls[0]["url"].endswith("/api/fund/performance/returns")
    assert session.calls[1]["url"].endswith("/api/fund/performance/drawdowns")


def test_fund_holdings_returns_summary_and_items():
    client, session = _client_with(
        [_envelope({"total_stock_ratio_pct": 92.1, "item": [{"thscode": "600519.SH"}]})]
    )
    data = client.fund_holdings("025480.OF")
    assert data["total_stock_ratio_pct"] == 92.1
    assert session.calls[0]["url"].endswith("/api/fund/portfolio/holdings")


# ---- T2：持有人 / 配置 / 经理 / 诊断 / 分红 / 公司 ----

def test_fund_holders_detail_scope_and_top_limit():
    client, session = _client_with(
        [_envelope({"item": []}), _envelope({"item": [], "limit": 10})]
    )
    client.fund_holders_detail("510300.SH", merge_scope="merged")
    client.fund_holders_top("510300.SH", limit=10)
    assert session.calls[0]["params"]["merge_scope"] == "merged"
    assert session.calls[1]["params"]["limit"] == 10


def test_fund_allocations_and_manager_and_company():
    client, session = _client_with([_envelope({"item": []}) for _ in range(4)])
    client.fund_asset_allocation("510300.SH")
    client.fund_industry_allocation("510300.SH")
    client.fund_manager_detail("m001")
    client.fund_company("c001")
    assert session.calls[0]["url"].endswith("/api/fund/portfolio/asset-allocation")
    assert session.calls[1]["url"].endswith("/api/fund/portfolio/industry-allocation")
    assert session.calls[2]["url"].endswith("/api/fund/managers/detail")
    assert session.calls[2]["params"] == {"manager_id": "m001"}
    assert session.calls[3]["url"].endswith("/api/fund/companies/detail")
    assert session.calls[3]["params"] == {"company_id": "c001"}


def test_fund_diagnostics_and_dividends():
    client, session = _client_with(
        [_envelope({"item": []}), _envelope({"dividend_count": 2, "item": []})]
    )
    client.fund_diagnostics("510300.SH")
    data = client.fund_dividends("510300.SH")
    assert data["dividend_count"] == 2
    assert session.calls[0]["url"].endswith("/api/fund/diagnostics/detail")
    assert session.calls[1]["url"].endswith("/api/fund/corporate-actions/dividends")


# ---- 错误码透传 ----

def test_fund_business_error_raises_fuyao_error():
    client, _ = _client_with(
        [FakeResponse(payload={"code": 3004, "message": "该基金类型不支持"})]
    )
    with pytest.raises(FuyaoError) as exc_info:
        client.fund_market_snapshot("025480.OF")
    assert str(exc_info.value.code) == "3004"
