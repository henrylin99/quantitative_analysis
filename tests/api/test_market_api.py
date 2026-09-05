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


class _FakeBoardService:
    def __init__(self):
        self.pool = {"date": "20260904", "total": 1, "items": []}
        self.ladder = {"days": []}
        self.boards = {"tag": "industry", "items": []}
        self.constituents = {"code": "881101.TI", "items": []}
        self.hot = {"period": "day", "hot": [], "skyrocket": []}
        self.search = {"query": "茅台", "items": []}
        self.kwargs = {}

    def get_limit_up_pool(self, date=None, page=1, size=100):
        self.kwargs["pool"] = (date, page, size)
        return self.pool

    def get_limit_down_pool(self, date=None, page=1, size=100):
        self.kwargs["down_pool"] = (date, page, size)
        return self.pool

    def get_limit_break_pool(self, date=None, page=1, size=100):
        self.kwargs["break_pool"] = (date, page, size)
        return self.pool

    def get_limit_up_ladder(self):
        return self.ladder

    def get_boards(self, tag):
        self.kwargs["tag"] = tag
        return self.boards

    def get_board_constituents(self, code):
        self.kwargs["board_code"] = code
        return self.constituents

    def get_hot_stocks(self, period="day"):
        self.kwargs["period"] = period
        return self.hot

    def search_tickers(self, query, limit=10):
        self.kwargs["search"] = (query, limit)
        return self.search


@pytest.fixture()
def fake_service(monkeypatch):
    service = _FakeService()
    board = _FakeBoardService()
    monkeypatch.setattr(
        "app.api.market_api.get_market_snapshot_service", lambda: service
    )
    monkeypatch.setattr(
        "app.api.market_api.get_board_market_service", lambda: board
    )
    service.board = board
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


def test_limit_up_pool_endpoint(app, fake_service):
    resp = app.test_client().get("/api/market/limit-up/pool?date=20260904&page=2&size=50")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["pool"] == ("20260904", 2, 50)


def test_limit_up_pool_validates_params(app, fake_service):
    assert (
        app.test_client().get("/api/market/limit-up/pool?date=2026-09-04").status_code == 400
    )
    assert app.test_client().get("/api/market/limit-up/pool?page=x").status_code == 400


def test_limit_down_and_break_pools(app, fake_service):
    resp = app.test_client().get("/api/market/limit-down/pool?date=20260904")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["down_pool"] == ("20260904", 1, 100)
    resp = app.test_client().get("/api/market/limit-break/pool?size=50")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["break_pool"] == (None, 1, 50)


def test_hot_stocks_endpoint(app, fake_service):
    assert app.test_client().get("/api/market/hot-stocks?period=week").status_code == 400
    resp = app.test_client().get("/api/market/hot-stocks?period=hour")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["period"] == "hour"


def test_ticker_search_endpoint(app, fake_service):
    assert app.test_client().get("/api/market/ticker-search?q=m").status_code == 400
    resp = app.test_client().get("/api/market/ticker-search?q=茅台")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["search"] == ("茅台", 10)


def test_limit_up_ladder_endpoint(app, fake_service):
    resp = app.test_client().get("/api/market/limit-up/ladder")
    assert resp.get_json()["data"] == {"days": []}


def test_boards_endpoint_validates_tag(app, fake_service):
    assert app.test_client().get("/api/market/boards?tag=sector").status_code == 400
    resp = app.test_client().get("/api/market/boards?tag=cn_concept")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["tag"] == "cn_concept"


def test_board_constituents_endpoint(app, fake_service):
    assert (
        app.test_client().get("/api/market/boards/constituents").status_code == 400
    )
    resp = app.test_client().get("/api/market/boards/constituents?code=881101.TI")
    assert resp.get_json()["code"] == 200
    assert fake_service.board.kwargs["board_code"] == "881101.TI"


def test_api_error_envelope_on_service_exception(app, monkeypatch):
    class _Boom:
        def get_dashboard(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.api.market_api.get_market_snapshot_service", lambda: _Boom())
    resp = app.test_client().get("/api/market/dashboard")
    assert resp.status_code == 500
    assert resp.get_json()["code"] == 500
