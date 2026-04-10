import pytest

from app.services.factor_engine import FactorEngine

pytestmark = pytest.mark.module_factor_engine


def test_builtin_factor_validation_samples_api_returns_core_samples(app):
    client = app.test_client()

    response = client.get("/api/ml-factor/factors/builtin-validation-samples")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    factor_ids = {item["factor_id"] for item in data["samples"]}
    assert {
        "momentum_5d",
        "volatility_20d",
        "volume_ratio_20d",
        "price_to_ma20",
        "money_flow_strength",
    }.issubset(factor_ids)

