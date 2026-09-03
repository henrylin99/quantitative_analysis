import pandas as pd

from app.services.parquet_state_store import ModelRepository, ParquetStateStore


def test_model_repository_round_trips_definitions_and_predictions(tmp_path):
    repo = ModelRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

    repo.upsert_definition(
        {
            "model_id": "model_a",
            "model_name": "模型A",
            "model_type": "xgboost",
            "factor_list": ["momentum_5d"],
            "target_type": "return_5d",
            "model_params": {"max_depth": 6},
            "training_config": {"test_size": 0.2},
        }
    )
    repo.save_predictions(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "model_id": "model_a", "predicted_return": 0.2, "rank_score": 2},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "model_id": "model_a", "predicted_return": 0.3, "rank_score": 1},
            ]
        )
    )

    definitions = repo.list_definitions()
    assert definitions[0]["factor_list"] == ["momentum_5d"]

    predictions = repo.get_predictions(model_id="model_a", trade_date="2024-06-04")
    assert predictions["ts_code"].tolist() == ["000001.SZ", "000002.SZ"]

    repo.delete_definition("model_a")
    assert repo.get_definition("model_a")["is_active"] is False
    assert repo.get_predictions(model_id="model_a").empty
