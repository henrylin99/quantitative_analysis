"""expected_returns 量纲合约：优化器必须拿到收益量纲，而不是排名/分数。"""
import numpy as np
import pandas as pd
import pytest

from app.api.ml_factor_api import (
    RETURNS_CALIBRATION_PERIOD_DAYS,
    _calibrate_scores_to_expected_returns,
)
from app.services.stock_scoring import StockScoringEngine

pytestmark = pytest.mark.module_scoring


def _engine() -> StockScoringEngine:
    return StockScoringEngine.__new__(StockScoringEngine)


def _predictions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "model_id": "m1", "predicted_return": 0.10, "probability_score": 0.9, "rank_score": 1},
            {"ts_code": "000001.SZ", "model_id": "m2", "predicted_return": 0.06, "probability_score": 0.8, "rank_score": 2},
            {"ts_code": "000002.SZ", "model_id": "m1", "predicted_return": -0.04, "probability_score": 0.2, "rank_score": 3},
            {"ts_code": "000002.SZ", "model_id": "m2", "predicted_return": -0.02, "probability_score": 0.3, "rank_score": 4},
        ]
    )


def test_average_ensemble_keeps_return_scale_column():
    result = _engine()._ensemble_predictions(_predictions(), "average")

    assert "predicted_return" in result.columns
    row1 = result[result["ts_code"] == "000001.SZ"].iloc[0]
    assert row1["ensemble_score"] == pytest.approx(0.08)
    assert row1["predicted_return"] == pytest.approx(0.08)


def test_rank_average_ensemble_separates_rank_score_from_returns():
    """rank_average 下 ensemble_score 是 1/rank（无量纲），predicted_return 必须
    单独保留收益量纲，否则会被当预期收益喂给优化器。"""
    result = _engine()._ensemble_predictions(_predictions(), "rank_average")

    assert "predicted_return" in result.columns
    top = result.iloc[0]
    assert top["ensemble_score"] == pytest.approx(1.0 / 1.5)
    assert top["predicted_return"] == pytest.approx(0.08)
    assert top["ensemble_score"] != pytest.approx(top["predicted_return"])


def test_weighted_average_ensemble_keeps_return_scale_column():
    result = _engine()._ensemble_predictions(_predictions(), "weighted_average")

    assert "predicted_return" in result.columns
    assert result["predicted_return"].notna().all()


class _FakeReader:
    """构造已知离散度的价格截面：A 股票 20 日 +10%，B 股票 -10%。"""

    def __init__(self, prices):
        self._prices = prices

    def get_return_prices(self, ts_codes=None, start_date=None, end_date=None):
        return self._prices.copy()


def _price_frame():
    rows = []
    for ts_code, target in (("000001.SZ", 110.0), ("000002.SZ", 90.0)):
        for i in range(RETURNS_CALIBRATION_PERIOD_DAYS + 1):
            close = 100.0 + (target - 100.0) * i / RETURNS_CALIBRATION_PERIOD_DAYS
            rows.append({"ts_code": ts_code, "trade_date": pd.Timestamp(2026, 6, 1) + pd.Timedelta(days=i), "close": close})
    return pd.DataFrame(rows)


def test_calibration_maps_scores_to_return_scale(monkeypatch):
    import app.api.ml_factor_api as api

    monkeypatch.setattr(api, "ParquetDataReader", lambda: _FakeReader(_price_frame()))
    scores = pd.Series({"000001.SZ": 1.0, "000002.SZ": 0.0})

    out = _calibrate_scores_to_expected_returns(scores, "2026-06-21", "mean_variance")

    # 排序不变；量纲与同期实际收益离散度一致（std = 0.10 * sqrt(2)）
    assert out["000001.SZ"] > out["000002.SZ"]
    assert out.abs().max() == pytest.approx(0.10, rel=1e-6)
    assert out.std() == pytest.approx(0.10 * np.sqrt(2), rel=1e-6)


def test_calibration_passthrough_for_methods_that_ignore_returns(monkeypatch):
    scores = pd.Series({"000001.SZ": 1.0, "000002.SZ": 0.0})

    out = _calibrate_scores_to_expected_returns(scores, "2026-06-21", "equal_weight")

    assert out.equals(scores)


def test_calibration_falls_back_to_zero_when_prices_missing(monkeypatch):
    import app.api.ml_factor_api as api

    monkeypatch.setattr(api, "ParquetDataReader", lambda: _FakeReader(pd.DataFrame()))
    scores = pd.Series({"000001.SZ": 1.0, "000002.SZ": 0.0})

    out = _calibrate_scores_to_expected_returns(scores, "2026-06-21", "mean_variance")

    # 数据不足时给零期望收益（优化退化为只看风险），而不是拿 0-1 分数冒充收益
    assert (out == 0).all()
