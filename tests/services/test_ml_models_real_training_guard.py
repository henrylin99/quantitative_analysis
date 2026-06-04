import pandas as pd
import types

import pytest

from app.services.ml_models import MLModelManager

pytestmark = [pytest.mark.module_ml_model, pytest.mark.milestone_m3_ml]


def test_create_model_definition_rejects_simulated_target_type(app):
    manager = MLModelManager()

    success = manager.create_model_definition(
        model_id="sim-model",
        model_name="Simulated Model",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="simulated_return",
    )

    assert success is False


def test_calculate_target_returns_requires_real_future_prices(app, monkeypatch):
    manager = MLModelManager()
    feature_df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": ["2024-01-02"],
            "factor_a": [1.0],
        }
    )
    # 只提供2天价格，不足以计算5日收益率
    price_df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "close": [10.0, 10.2],
        }
    )

    fake_reader = types.SimpleNamespace(
        get_daily=lambda **kwargs: price_df,
    )
    monkeypatch.setattr("app.services.ml_models.ParquetDataReader", lambda: fake_reader)

    target_df = manager._calculate_target_returns(feature_df, "return_5d")

    assert target_df.empty
