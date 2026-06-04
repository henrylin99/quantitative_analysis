from pathlib import Path

import pytest

from app.services.ml_models import MLModelManager
from app.services.parquet_state_store import ParquetStateStore

pytestmark = pytest.mark.module_ml_model


def test_delete_model_removes_definition_predictions_files_and_cache(app, tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.model_dir = str(tmp_path)

    manager.create_model_definition(
        model_id="delete-me",
        model_name="Delete Me",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_5d",
    )
    manager.save_predictions(
        __import__("pandas").DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2024-01-02",
                    "model_id": "delete-me",
                    "predicted_return": 0.1,
                    "probability_score": 0.5,
                    "rank_score": 1,
                }
            ]
        )
    )

    model_file = tmp_path / "delete-me.pkl"
    scaler_file = tmp_path / "delete-me_scaler.pkl"
    model_file.write_text("model", encoding="utf-8")
    scaler_file.write_text("scaler", encoding="utf-8")
    manager.models["delete-me"] = object()
    manager.scalers["delete-me"] = object()

    result = manager.delete_model("delete-me")

    assert result["success"] is True
    assert manager.model_repo.get_definition("delete-me")["is_active"] is False
    assert manager.model_repo.get_predictions(model_id="delete-me").empty
    assert not model_file.exists()
    assert not scaler_file.exists()
    assert "delete-me" not in manager.models
    assert "delete-me" not in manager.scalers


def test_delete_model_returns_not_found_for_missing_definition(app, tmp_path):
    manager = MLModelManager()
    manager.model_dir = str(tmp_path)

    result = manager.delete_model("missing-model")

    assert result["success"] is False
    assert "未找到模型定义" in result["error"]
