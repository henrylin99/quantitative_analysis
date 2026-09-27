"""fund_api 契约测试（fake 服务注入）。"""

import pytest
from flask import Flask

from app.api.fund_api import fund_bp

pytestmark = pytest.mark.module_data_jobs


class FakeFundService:
    def __init__(self):
        self.profile = {"thscode": "510300.SH", "fund_name": "沪深300ETF"}
        self.snapshot = {"thscode": "510300.SH", "last_price": 4.01}
        self.history = {"items": [{"date": "20250702", "close": 4.01}]}
        self.performance = {"returns": {"return_year": 12.5}}
        self.holdings = {"items": [], "summary": {}}
        self.kwargs = {}
        self.fuyao_error = None

    def _maybe_raise(self, thscode):
        if self.fuyao_error is not None:
            raise self.fuyao_error

    def get_profile(self, thscode):
        self.kwargs["profile"] = thscode
        self._maybe_raise(thscode)
        return self.profile

    def get_snapshot(self, thscode):
        self.kwargs["snapshot"] = thscode
        self._maybe_raise(thscode)
        return self.snapshot

    def get_history(self, thscode, start, end):
        self.kwargs["history"] = (thscode, start, end)
        if start > end:
            raise ValueError(f"start 不能晚于 end: {start} > {end}")
        return self.history

    def get_performance(self, thscode):
        self.kwargs["performance"] = thscode
        self._maybe_raise(thscode)
        return self.performance

    def get_holdings(self, thscode):
        self.kwargs["holdings"] = thscode
        self._maybe_raise(thscode)
        return self.holdings

    def get_holders(self, thscode):
        self.kwargs["holders"] = thscode
        return {"structure": [], "top": []}

    def get_dividends(self, thscode):
        self.kwargs["dividends"] = thscode
        return {"items": []}

    def get_asset_allocation(self, thscode):
        self.kwargs["asset"] = thscode
        self._maybe_raise(thscode)
        return []

    def get_industry_allocation(self, thscode):
        self.kwargs["industry"] = thscode
        self._maybe_raise(thscode)
        return []

    def get_diagnostics(self, thscode):
        self.kwargs["diagnostics"] = thscode
        return {}

    def get_manager(self, manager_id):
        self.kwargs["manager"] = manager_id
        return {"manager_name": "张三"}

    def get_company(self, company_id):
        self.kwargs["company"] = company_id
        return {"company_name": "某基金公司"}


@pytest.fixture()
def app(monkeypatch):
    fake = FakeFundService()
    monkeypatch.setattr("app.api.fund_api.get_fund_service", lambda: fake)
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(fund_bp)
    app.extensions["fake_fund_service"] = fake
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def _fake(app) -> FakeFundService:
    return app.extensions["fake_fund_service"]


# ---- 参数校验 ----

def test_profile_requires_thscode(client):
    resp = client.get("/api/fund/profile")
    assert resp.status_code == 400


def test_profile_rejects_bad_thscode_format(client):
    resp = client.get("/api/fund/profile", query_string={"thscode": "510300"})
    assert resp.status_code == 400
    assert "格式非法" in resp.get_json()["message"]


def test_history_requires_start_end(client):
    resp = client.get("/api/fund/history", query_string={"thscode": "510300.SH"})
    assert resp.status_code == 400


def test_history_rejects_reversed_window(client):
    resp = client.get(
        "/api/fund/history",
        query_string={"thscode": "510300.SH", "start": "20250702", "end": "20250601"},
    )
    assert resp.status_code == 400


# ---- 正常链路 ----

def test_profile_returns_envelope(client, app):
    resp = client.get("/api/fund/profile", query_string={"thscode": "510300.SH"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["fund_name"] == "沪深300ETF"
    assert _fake(app).kwargs["profile"] == "510300.SH"


def test_history_passes_window(client, app):
    resp = client.get(
        "/api/fund/history",
        query_string={"thscode": "510300.SH", "start": "20250101", "end": "20250702"},
    )
    assert resp.status_code == 200
    assert _fake(app).kwargs["history"] == ("510300.SH", "20250101", "20250702")


def test_manager_requires_manager_id(client):
    resp = client.get("/api/fund/manager")
    assert resp.status_code == 400


def test_company_passes_company_id(client, app):
    resp = client.get("/api/fund/company", query_string={"company_id": "c001"})
    assert resp.status_code == 200
    assert _fake(app).kwargs["company"] == "c001"


# ---- 错误映射 ----

def test_unsupported_fund_type_maps_to_404(app, client):
    from app.utils.data_sources.fuyao_client import FuyaoError

    _fake(app).fuyao_error = FuyaoError("3004", "该基金类型不支持")
    resp = client.get("/api/fund/snapshot", query_string={"thscode": "025480.OF"})
    assert resp.status_code == 404


def test_not_found_fund_maps_to_404(app, client):
    from app.utils.data_sources.fuyao_client import FuyaoError

    _fake(app).fuyao_error = FuyaoError("3001", "标的不存在")
    resp = client.get("/api/fund/profile", query_string={"thscode": "999999.OF"})
    assert resp.status_code == 404


def test_data_not_ready_maps_to_502(app, client):
    from app.utils.data_sources.fuyao_client import FuyaoError

    _fake(app).fuyao_error = FuyaoError("3002", "数据未就绪")
    resp = client.get("/api/fund/performance", query_string={"thscode": "510300.SH"})
    assert resp.status_code == 502


def test_rate_limit_maps_to_502(app, client):
    from app.utils.data_sources.fuyao_client import FuyaoError

    _fake(app).fuyao_error = FuyaoError("4001", "限频")
    resp = client.get("/api/fund/holdings", query_string={"thscode": "510300.SH"})
    assert resp.status_code == 502


# ---- 净值序列 ----

def test_nav_requires_valid_range(client, app):
    fake = _fake(app)
    fake.nav_series: list = []
    fake.get_nav_series = lambda thscode, range="year": fake.nav_series  # type: ignore[method-assign]

    bad = client.get("/api/fund/nav", query_string={"thscode": "025480.OF", "range": "bad"})
    assert bad.status_code == 400

    ok = client.get("/api/fund/nav", query_string={"thscode": "025480.OF", "range": "year"})
    assert ok.status_code == 200


def test_upstream_no_data_maps_to_404(app, client):
    from app.utils.data_sources.fuyao_client import FuyaoError

    _fake(app).fuyao_error = FuyaoError("5003", "Fund industry allocation status 9999")
    resp = client.get("/api/fund/industry-allocation", query_string={"thscode": "510300.SH"})
    assert resp.status_code == 404


# ---- 基金检索 ----

def test_search_requires_query(client):
    resp = client.get("/api/fund/search")
    assert resp.status_code == 400


def test_search_rejects_bad_asset_type(client):
    resp = client.get("/api/fund/search", query_string={"q": "300", "asset_type": "fund"})
    assert resp.status_code == 400


def test_search_passes_query_and_filter(client, app):
    fake = _fake(app)
    fake.search_result: list = []

    def _search(query, asset_type=None, limit=20):
        fake.kwargs["search"] = (query, asset_type, limit)
        return fake.search_result

    fake.search_funds = _search  # type: ignore[method-assign]

    resp = client.get(
        "/api/fund/search", query_string={"q": "300", "asset_type": "fund-etf", "limit": 10}
    )
    assert resp.status_code == 200
    assert _fake(app).kwargs["search"] == ("300", "fund-etf", 10)
