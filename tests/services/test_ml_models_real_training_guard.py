import pandas as pd
import types

from app.services.ml_models import MLModelManager


def test_calculate_target_returns_requires_real_future_prices(app, monkeypatch):
    manager = MLModelManager()
    feature_df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": ["2024-01-02"],
            "factor_a": [1.0],
        }
    )
    price_df = pd.DataFrame(
        {
            "trade_date": ["2024-01-02", "2024-01-03"],
            "close": [10.0, 10.2],
            "pct_chg": [0.0, 2.0],
        }
    )

    class FakeQuery:
        statement = object()

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

    fake_query = FakeQuery()
    fake_model = types.SimpleNamespace(
        query=fake_query,
        ts_code="ts_code",
        trade_date="trade_date",
    )
    monkeypatch.setattr("app.services.ml_models.StockDailyHistory", fake_model)
    monkeypatch.setattr("app.services.ml_models.pd.read_sql", lambda statement, engine: price_df)

    target_df = manager._calculate_target_returns(feature_df, "return_5d")

    assert target_df.empty
