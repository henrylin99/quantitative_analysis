"""因子覆盖日期合约：引擎按集合反查最近覆盖日期并带近半年回退；API 只做委托。"""
import pandas as pd
import pytest

from app.services.parquet_state_store import ParquetStateStore
from app.services.stock_scoring import StockScoringEngine

pytestmark = pytest.mark.module_scoring


class StubFactorRepo:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get_values(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0) if self.results else pd.DataFrame()


def build_engine(tmp_path):
    engine = StockScoringEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    return engine


def test_recent_coverage_returns_latest_date(tmp_path):
    engine = build_engine(tmp_path)
    stub = StubFactorRepo([pd.DataFrame({"trade_date": ["20260801", "20260901"]})])
    engine.factor_repo = stub

    result = engine.latest_factor_coverage_date(["momentum_20"])

    assert result == "2026-09-01"
    assert stub.calls[0]["factor_ids"] == ["momentum_20"]
    assert len(stub.calls[0]["start_date"]) == 8


def test_falls_back_to_full_range_when_recent_window_empty(tmp_path):
    engine = build_engine(tmp_path)
    stub = StubFactorRepo([
        pd.DataFrame(),
        pd.DataFrame({"trade_date": ["20250101"]}),
    ])
    engine.factor_repo = stub

    result = engine.latest_factor_coverage_date(["financial_factor"])

    assert result == "2025-01-01"
    assert len(stub.calls) == 2
    assert "start_date" not in stub.calls[1]


def test_no_data_returns_none(tmp_path):
    engine = build_engine(tmp_path)
    engine.factor_repo = StubFactorRepo([pd.DataFrame(), pd.DataFrame()])

    assert engine.latest_factor_coverage_date(["any"]) is None


def test_no_data_without_factor_ids_skips_fallback(tmp_path):
    engine = build_engine(tmp_path)
    stub = StubFactorRepo([pd.DataFrame()])
    engine.factor_repo = stub

    assert engine.latest_factor_coverage_date(None) is None
    assert len(stub.calls) == 1


def test_unparsable_trade_dates_return_none(tmp_path):
    engine = build_engine(tmp_path)
    engine.factor_repo = StubFactorRepo([pd.DataFrame({"trade_date": ["not-a-date"]})])

    assert engine.latest_factor_coverage_date(["any"]) is None


def test_endpoint_delegates_to_engine_and_maps_none_to_404(app, monkeypatch):
    import app.api.ml_factor_api as ml_factor_api

    class StubEngine:
        def __init__(self, result):
            self.result = result
            self.seen = None

        def latest_factor_coverage_date(self, factor_ids):
            self.seen = factor_ids
            return self.result

    good = StubEngine("2026-09-01")
    monkeypatch.setattr(ml_factor_api, "get_scoring_engine", lambda: good)
    response = app.test_client().get("/api/ml-factor/factors/latest-coverage-date?factor_ids=momentum_20,ratio_roe")
    assert response.status_code == 200
    body = response.get_json()
    assert body == {
        "success": True,
        "latest_coverage_date": "2026-09-01",
        "factor_ids": ["momentum_20", "ratio_roe"],
    }
    assert good.seen == ["momentum_20", "ratio_roe"]

    empty = StubEngine(None)
    monkeypatch.setattr(ml_factor_api, "get_scoring_engine", lambda: empty)
    response = app.test_client().get("/api/ml-factor/factors/latest-coverage-date")
    assert response.status_code == 404
    assert response.get_json()["success"] is False
