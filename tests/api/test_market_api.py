"""market_api / datasources_api 契约测试（fake 服务注入）。"""

import pytest
from flask import Flask

from app.api.market_api import datasources_bp, market_bp

pytestmark = pytest.mark.module_data_jobs


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(market_bp)
    app.register_blueprint(datasources_bp)
    return app


class _FakeService:
    def __init__(self):
        self.quotes = {}
        self.dashboard = {"breadth": {"up": 1}, "degraded": False}
        self.indices = [{"ts_code": "000001.SH", "last_price": 3000.0, "pct_chg": 0.5}]
        self.dragon = {"trade_date": "20260904"}
        self.auction = {"item": []}
        self.status = {"tushare": {"configured": True}}
        self.kwargs = {}

    def get_quotes(self, codes):
        self.kwargs["codes"] = codes
        return {c: {"ts_code": c} for c in codes}

    def get_dashboard(self):
        return self.dashboard

    def get_indices(self, symbols=None):
        self.kwargs["indices"] = symbols
        return self.indices

    def get_dragon_tiger(self, board_type="all", date=None):
        self.kwargs["dragon"] = (board_type, date)
        return self.dragon

    def get_auction_benchmark(self, date=None):
        self.kwargs["auction"] = date
        return self.auction

    def get_source_status(self, force=False):
        self.kwargs["force"] = force
        return self.status


@pytest.fixture()
def fake_service(monkeypatch):
    service = _FakeService()
    monkeypatch.setattr(
        "app.api.market_api.get_market_snapshot_service", lambda: service
    )
    return service


def test_snapshot_requires_codes(app):
    resp = app.test_client().get("/api/market/snapshot")
    assert resp.status_code == 400


def test_snapshot_returns_envelope(app, fake_service):
    resp = app.test_client().get("/api/market/snapshot?codes=600000.SH,000001.SZ")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["code"] == 200
    assert set(payload["data"]["quotes"]) == {"600000.SH", "000001.SZ"}
    assert fake_service.kwargs["codes"] == ["600000.SH", "000001.SZ"]


def test_dashboard_endpoint(app, fake_service):
    resp = app.test_client().get("/api/market/dashboard")
    assert resp.get_json()["data"]["breadth"]["up"] == 1


def test_indices_endpoint_default_and_custom(app, fake_service):
    app.test_client().get("/api/market/indices")
    assert fake_service.kwargs["indices"] is None
    app.test_client().get("/api/market/indices?codes=399001.SZ")
    assert fake_service.kwargs["indices"] == ["399001.SZ"]


def test_dragon_tiger_validates_board(app, fake_service):
    resp = app.test_client().get("/api/market/dragon-tiger?board=wrong")
    assert resp.status_code == 400
    resp = app.test_client().get("/api/market/dragon-tiger?board=org&date=20260904")
    assert resp.get_json()["code"] == 200
    assert fake_service.kwargs["dragon"] == ("org", "20260904")


def test_auction_benchmark_endpoint(app, fake_service):
    resp = app.test_client().get("/api/market/auction-benchmark?date=20260903")
    assert resp.get_json()["code"] == 200
    assert fake_service.kwargs["auction"] == "20260903"


def test_datasource_status_endpoint(app, fake_service):
    resp = app.test_client().get("/api/datasources/status?force=1")
    assert resp.get_json()["data"]["tushare"]["configured"] is True
    assert fake_service.kwargs["force"] is True


def test_api_error_envelope_on_service_exception(app, monkeypatch):
    class _Boom:
        def get_dashboard(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.api.market_api.get_market_snapshot_service", lambda: _Boom())
    resp = app.test_client().get("/api/market/dashboard")
    assert resp.status_code == 500
    assert resp.get_json()["code"] == 500
