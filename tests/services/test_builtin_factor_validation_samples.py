import math

import pandas as pd
import pytest

from app.services.factor_engine import FactorEngine

pytestmark = pytest.mark.module_factor_engine


def _history_frame(close_values, volume_values):
    return {
        "history": pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * len(close_values),
                "trade_date": pd.date_range("2024-01-01", periods=len(close_values), freq="D"),
                "close": close_values,
                "vol": volume_values,
            }
        )
    }


def test_momentum_5d_validation_sample_matches_formula():
    engine = FactorEngine()
    data = _history_frame([10, 11, 12, 13, 14, 15], [100, 100, 100, 100, 100, 100])

    result = engine._momentum_factor(data, "momentum_5d")

    assert len(result) == 1
    assert math.isclose(result.iloc[-1]["factor_value"], 0.5, rel_tol=1e-9)


def test_volatility_20d_validation_sample_matches_formula():
    engine = FactorEngine()
    close_values = list(range(100, 121))
    data = _history_frame(close_values, [1000] * len(close_values))

    result = engine._volatility_factor(data, "volatility_20d")

    expected = pd.Series(close_values).pct_change().rolling(20).std().iloc[-1]
    assert len(result) == 1
    assert math.isclose(result.iloc[-1]["factor_value"], expected, rel_tol=1e-9)


def test_volume_ratio_20d_validation_sample_matches_formula():
    engine = FactorEngine()
    volumes = list(range(1, 22))
    data = _history_frame(list(range(100, 121)), volumes)

    result = engine._volume_ratio_factor(data, "volume_ratio_20d")

    expected = volumes[-1] / (sum(volumes[-20:]) / 20)
    assert len(result) == 2
    assert math.isclose(result.iloc[-1]["factor_value"], expected, rel_tol=1e-9)


def test_price_to_ma20_validation_sample_matches_formula():
    engine = FactorEngine()
    close_values = list(range(1, 22))
    data = _history_frame(close_values, [1000] * len(close_values))

    result = engine._price_to_ma_factor(data, "price_to_ma20")

    expected = close_values[-1] / (sum(close_values[-20:]) / 20) - 1
    assert len(result) == 2
    assert math.isclose(result.iloc[-1]["factor_value"], expected, rel_tol=1e-9)


def test_money_flow_strength_validation_sample_matches_formula():
    engine = FactorEngine()
    data = {
        "moneyflow": pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": [pd.Timestamp("2024-01-01")],
                "buy_sm_amount": [100.0],
                "buy_md_amount": [200.0],
                "buy_lg_amount": [300.0],
                "buy_elg_amount": [400.0],
                "sell_lg_amount": [50.0],
                "sell_elg_amount": [25.0],
            }
        )
    }

    result = engine._money_flow_strength_factor(data, "money_flow_strength")

    expected = ((300.0 + 400.0) - (50.0 + 25.0)) / (100.0 + 200.0 + 300.0 + 400.0)
    assert len(result) == 1
    assert math.isclose(result.iloc[-1]["factor_value"], expected, rel_tol=1e-9)


def test_builtin_factor_validation_samples_include_field_dependencies():
    engine = FactorEngine()

    samples = engine.get_builtin_factor_validation_samples()
    sample_map = {item["factor_id"]: item for item in samples}

    assert "close" in sample_map["momentum_5d"]["required_fields"]
    assert "vol" in sample_map["volume_ratio_20d"]["required_fields"]
    assert sample_map["money_flow_strength"]["calculation_rule"]
