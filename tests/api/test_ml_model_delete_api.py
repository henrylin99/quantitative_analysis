from unittest.mock import patch


def test_delete_model_api_returns_success_snapshot(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_ml_manager") as get_manager:
        get_manager.return_value.delete_model.return_value = {
            "success": True,
            "model_id": "delete-me",
            "deleted_prediction_count": 3,
            "deleted_files": ["models/delete-me.pkl", "models/delete-me_scaler.pkl"],
        }

        response = client.delete("/api/ml-factor/models/delete-me")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["model_id"] == "delete-me"


def test_delete_model_api_returns_404_for_missing_model(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_ml_manager") as get_manager:
        get_manager.return_value.delete_model.return_value = {
            "success": False,
            "error": "未找到模型定义: missing-model",
        }

        response = client.delete("/api/ml-factor/models/missing-model")

    assert response.status_code == 404
    data = response.get_json()
    assert "未找到模型定义" in data["error"]
