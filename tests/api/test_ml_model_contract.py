def test_create_model_rejects_simulated_target_type(app):
    client = app.test_client()

    response = client.post(
        "/api/ml-factor/models/create",
        json={
            "model_id": "sim-model",
            "model_name": "Simulated Model",
            "model_type": "random_forest",
            "factor_list": ["factor_a"],
            "target_type": "simulated_return",
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "target_type" in data["error"]
    assert "simulated_return" in data["error"]
