from unittest.mock import patch

import pandas as pd
import pytest

from app.services.factor_engine import FactorEngine
from app.services.parquet_state_store import ParquetStateStore

pytestmark = pytest.mark.module_factor_engine


def test_factors_list_includes_custom_factor_from_parquet_state(app, tmp_path):
    engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    engine.create_factor_definition(
        factor_id="custom_alpha",
        factor_name="自定义Alpha",
        factor_formula="close.pct_change(1)",
        factor_type="technical",
        description="demo",
        params={"window": 1},
    )

    client = app.test_client()
    with patch("app.api.ml_factor_api.get_factor_engine", return_value=engine):
        response = client.get("/api/ml-factor/factors/list?factor_type=technical&is_active=true")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert any(item["factor_id"] == "custom_alpha" for item in data["factors"])


def test_factors_calculate_persists_values_without_mysql(app, tmp_path):
    engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    engine.create_factor_definition(
        factor_id="custom_alpha",
        factor_name="自定义Alpha",
        factor_formula="close.pct_change(1)",
        factor_type="technical",
        description="demo",
        params={"window": 1},
    )

    client = app.test_client()
    sample_basic = pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"]})
    sample_daily = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "2024-06-03", "close": 10.0, "open": 9.5, "high": 10.1, "low": 9.2, "pre_close": 9.0, "change": 1.0, "pct_chg": 1.0, "vol": 100, "amount": 1000},
            {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "close": 11.0, "open": 10.0, "high": 11.2, "low": 9.8, "pre_close": 10.0, "change": 1.0, "pct_chg": 10.0, "vol": 110, "amount": 1100},
            {"ts_code": "000002.SZ", "trade_date": "2024-06-03", "close": 20.0, "open": 19.5, "high": 20.1, "low": 19.2, "pre_close": 19.0, "change": 1.0, "pct_chg": 1.0, "vol": 200, "amount": 2000},
            {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "close": 22.0, "open": 20.0, "high": 22.2, "low": 19.8, "pre_close": 20.0, "change": 2.0, "pct_chg": 10.0, "vol": 210, "amount": 2100},
        ]
    )

    with (
        patch("app.api.ml_factor_api.get_factor_engine", return_value=engine),
        patch("app.api.ml_factor_api._data_reader.get_stock_basic", return_value=sample_basic),
        patch.object(engine.data_reader, "get_daily", return_value=sample_daily),
    ):
        response = client.post(
            "/api/ml-factor/factors/calculate",
            json={"trade_date": "2024-06-04", "factor_ids": ["custom_alpha"]},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["results"][0]["saved"] is True

    saved = engine.factor_repo.get_values(factor_ids=["custom_alpha"], trade_date="2024-06-04")
    assert not saved.empty
    assert saved["factor_id"].unique().tolist() == ["custom_alpha"]
