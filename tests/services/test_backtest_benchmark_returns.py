from datetime import date
import sys
import types

import pytest

if "xgboost" not in sys.modules:
    sys.modules["xgboost"] = types.SimpleNamespace(
        XGBRegressor=object,
        XGBClassifier=object,
    )

if "lightgbm" not in sys.modules:
    sys.modules["lightgbm"] = types.SimpleNamespace(
        LGBMRegressor=object,
        LGBMClassifier=object,
    )

if "cvxpy" not in sys.modules:
    sys.modules["cvxpy"] = types.SimpleNamespace()

from app.services.backtest_engine import BacktestEngine

pytestmark = pytest.mark.module_backtest


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


def test_get_benchmark_returns_non_empty(monkeypatch):
    rows = [
        (date(2025, 1, 2), 100.0),
        (date(2025, 1, 3), 101.0),
        (date(2025, 1, 6), 99.0),
    ]

    def _fake_query(*args, **kwargs):
        return _FakeQuery(rows)

    monkeypatch.setattr("app.services.backtest_engine.db.session.query", _fake_query)

    engine = BacktestEngine()
    benchmark_returns = engine._get_benchmark_returns("2025-01-02", "2025-01-06")

    assert len(benchmark_returns) == 3
    assert benchmark_returns[1]["daily_return"] == pytest.approx(0.01)
    assert benchmark_returns[-1]["cumulative_return"] == pytest.approx(-0.01)
