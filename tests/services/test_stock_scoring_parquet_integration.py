import pandas as pd

from app.services.parquet_state_store import ParquetStateStore
from app.services.stock_scoring import StockScoringEngine


def test_ml_based_selection_reads_predictions_from_parquet(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    engine = StockScoringEngine(state_store=store)

    engine.model_repo.upsert_definition(
        {
            "model_id": "model_a",
            "model_name": "模型A",
            "model_type": "random_forest",
            "factor_list": ["factor_a"],
            "target_type": "return_5d",
            "model_params": {},
            "training_config": {},
        }
    )
    engine.model_repo.save_predictions(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "model_id": "model_a", "predicted_return": 0.2, "probability_score": 0.8, "rank_score": 1},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "model_id": "model_a", "predicted_return": 0.1, "probability_score": 0.2, "rank_score": 2},
            ]
        )
    )

    result = engine.ml_based_selection("2024-06-04", ["model_a"], top_n=2)
    assert [row["ts_code"] for row in result] == ["000001.SZ", "000002.SZ"]
    assert result[0]["model_count"] == 1


def test_factor_based_scoring_falls_back_to_factor_value_when_z_score_missing(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    engine = StockScoringEngine(state_store=store)

    engine.factor_repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "factor_a", "factor_value": 1.0},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "factor_a", "factor_value": 3.0},
            ]
        )
    )

    scores = engine.calculate_factor_scores("2024-06-04", ["factor_a"])

    assert list(scores.columns) == ["factor_a"]
    assert scores.loc["000001.SZ", "factor_a"] == 1.0
    assert scores.loc["000002.SZ", "factor_a"] == 3.0
