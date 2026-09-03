from unittest.mock import patch

import pandas as pd
import pytest

from app.services.ml_models import MLModelManager
from app.services.parquet_state_store import ParquetStateStore

pytestmark = pytest.mark.module_ml_model


def test_models_create_and_list_use_parquet_model_state(app, tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_ml_manager", return_value=manager):
        response = client.post(
            "/api/ml-factor/models/create",
            json={
                "model_id": "model_a",
                "model_name": "模型A",
                "model_type": "random_forest",
                "factor_list": ["factor_a", "factor_b"],
                "target_type": "return_5d",
            },
        )
        assert response.status_code == 200
        assert response.get_json()["success"] is True

        response = client.get("/api/ml-factor/models/list")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["models"][0]["model_id"] == "model_a"
    assert data["models"][0]["factor_list"] == ["factor_a", "factor_b"]


def test_models_detail_endpoint_returns_model_snapshot(app, tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_5d",
        training_config={"validation_method": "none"},
    )
    manager.model_repo.save_predictions(
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2024-06-04",
                    "model_id": "model_a",
                    "predicted_return": 0.2,
                    "rank_score": 1,
                }
            ]
        )
    )

    client = app.test_client()
    with patch("app.api.ml_factor_api.get_ml_manager", return_value=manager):
        response = client.get("/api/ml-factor/models/model_a")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["model"]["model_id"] == "model_a"
    assert data["model"]["prediction_summary"]["total_predictions"] == 1
    assert data["model"]["recent_predictions"][0]["ts_code"] == "000001.SZ"


def test_latest_prediction_date_endpoint_returns_newest_trade_date(app, tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_5d",
        training_config={"validation_method": "none"},
    )
    manager.model_repo.save_predictions(
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2024-06-04",
                    "model_id": "model_a",
                    "predicted_return": 0.2,
                    "rank_score": 1,
                },
                {
                    "ts_code": "000002.SZ",
                    "trade_date": "2024-06-05",
                    "model_id": "model_a",
                    "predicted_return": 0.1,
                    "rank_score": 2,
                },
            ]
        )
    )

    client = app.test_client()
    with patch("app.api.ml_factor_api.get_ml_manager", return_value=manager):
        response = client.get("/api/ml-factor/scoring/latest-prediction-date")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["latest_trade_date"] == "2024-06-05"
