import pytest
import pandas as pd

from app.services.factor_engine import FactorEngine
from app.services.parquet_state_store import ParquetStateStore

pytestmark = pytest.mark.module_factor_engine


def test_factor_engine_persists_and_reloads_custom_definitions(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    engine = FactorEngine(state_store=store)

    assert engine.create_factor_definition(
        factor_id="custom_alpha",
        factor_name="自定义Alpha",
        factor_formula="close.pct_change(1)",
        factor_type="technical",
        description="demo",
        params={"window": 1},
    )

    reloaded = FactorEngine(state_store=store)
    factor_ids = [item["factor_id"] for item in reloaded.get_factor_list("technical", True)]
    assert "custom_alpha" in factor_ids


def test_factor_engine_saves_and_reads_factor_values_from_parquet(tmp_path):
    engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    engine.create_factor_definition(
        factor_id="custom_alpha",
        factor_name="自定义Alpha",
        factor_formula="close.pct_change(1)",
        factor_type="technical",
        description="demo",
        params={"window": 1},
    )

    frame = pd.DataFrame(
        [
            {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "custom_alpha", "factor_value": 0.2, "percentile_rank": 80, "z_score": 1.0},
            {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "custom_alpha", "factor_value": 0.1, "percentile_rank": 20, "z_score": -1.0},
        ]
    )

    assert engine.save_factor_values(frame)

    exposure = engine.get_factor_exposure("custom_alpha", "2024-06-04")
    assert exposure["ts_code"].tolist() == ["000002.SZ", "000001.SZ"]
    # 因子库落库统一 float32（省一半存储），断言用近似比较
    assert exposure["factor_value"].tolist() == pytest.approx([0.2, 0.1])
