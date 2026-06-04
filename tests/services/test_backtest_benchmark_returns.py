import sys
import types

import pandas as pd
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


def test_get_benchmark_returns_non_empty(monkeypatch):
    # 构造模拟 parquet 返回的 DataFrame
    price_df = pd.DataFrame({
        "ts_code": ["000300.SH", "000300.SH", "000300.SH"],
        "trade_date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
        "close": [100.0, 101.0, 99.0],
    })

    fake_reader = types.SimpleNamespace(
        get_daily=lambda **kwargs: price_df,
    )
    monkeypatch.setattr("app.services.backtest_engine.ParquetDataReader", lambda: fake_reader)

    engine = BacktestEngine()
    benchmark_returns = engine._get_benchmark_returns("2025-01-02", "2025-01-06")

    assert len(benchmark_returns) == 3
    assert benchmark_returns[1]["daily_return"] == pytest.approx(0.01)
    assert benchmark_returns[-1]["cumulative_return"] == pytest.approx(-0.01)
