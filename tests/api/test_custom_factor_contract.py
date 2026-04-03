from unittest.mock import patch


def test_create_custom_factor_rejects_invalid_formula(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_factor_engine") as get_engine:
        get_engine.return_value.validate_custom_factor_formula.return_value = {
            "valid": False,
            "error": "column not allowed: revenue",
        }

        response = client.post(
            "/api/ml-factor/factors/custom",
            json={
                "factor_id": "bad_factor",
                "factor_name": "Bad Factor",
                "factor_formula": "revenue / close",
                "factor_type": "other",
            },
        )

    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "column not allowed: revenue"


def test_get_custom_factor_capabilities_returns_whitelist(app):
    client = app.test_client()

    with patch("app.api.ml_factor_api.get_factor_engine") as get_engine:
        get_engine.return_value.get_custom_factor_capabilities.return_value = {
            "allowed_columns": ["close", "vol"],
            "allowed_series_methods": ["pct_change", "rolling"],
            "allowed_window_methods": ["mean", "std"],
            "allowed_functions": ["abs"],
            "examples": ["close.pct_change(5)", "abs(close - open)"],
        }

        response = client.get("/api/ml-factor/factors/custom-capabilities")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "close" in data["capabilities"]["allowed_columns"]
    assert "rolling" in data["capabilities"]["allowed_series_methods"]
