from unittest.mock import patch


def test_train_model_response_does_not_include_demo_defaults(app):
    client = app.test_client()
    payload = {"model_id": "demo", "start_date": "2024-01-01", "end_date": "2024-01-31"}

    with patch("app.api.ml_factor_api.get_ml_manager") as get_manager:
        get_manager.return_value.train_model.return_value = {
            "success": True,
            "metrics": {"train_r2": 0.1, "sample_count": 12},
        }

        response = client.post("/api/ml-factor/models/train", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert "model_size" not in data
    assert "accuracy" not in data
    assert "loss" not in data
    assert data["training_samples"] == 12
