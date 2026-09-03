import pandas as pd

from app.services.parquet_state_store import FactorRepository, ParquetStateStore
import pytest

pytestmark = pytest.mark.module_factor_engine


def test_factor_repository_overwrites_existing_values_by_business_key(tmp_path):
    repo = FactorRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

    repo.upsert_definition(
        {
            "factor_id": "value_factor",
            "factor_name": "示例因子",
            "factor_formula": "close",
            "factor_type": "technical",
        }
    )
    repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "value_factor", "factor_value": 1.0},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "value_factor", "factor_value": 2.0},
            ]
        )
    )

    repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "value_factor", "factor_value": 9.5},
            ]
        )
    )

    frame = repo.get_values(factor_ids=["value_factor"], trade_date="2024-06-04")
    assert frame.loc[frame["ts_code"] == "000001.SZ", "factor_value"].iloc[0] == 9.5
    assert frame["ts_code"].tolist() == ["000001.SZ", "000002.SZ"]
