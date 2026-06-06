from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_create_portfolio_position_endpoint_creates_first_position(app, tmp_path):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "ts_code": "000001.SZ",
        "position_size": 1000,
        "avg_cost": 12.5,
        "sector": "银行",
    }

    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

    with patch("app.api.realtime_risk._portfolio_repo", repo):
        response = client.post("/api/realtime-analysis/risk/portfolio", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["portfolio_id"] == "growth_a"
    assert data["data"]["ts_code"] == "000001.SZ"


def test_create_portfolio_position_endpoint_rejects_duplicate_stock(app, tmp_path):
    client = app.test_client()

    payload = {
        "portfolio_id": "growth_a",
        "ts_code": "000001.SZ",
        "position_size": 1000,
        "avg_cost": 12.5,
    }

    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    # 先插入一条相同股票
    repo.upsert_position({
        "portfolio_id": "growth_a",
        "ts_code": "000001.SZ",
        "position_size": 500,
        "avg_cost": 10.0,
        "current_price": 10.0,
        "market_value": 5000,
        "is_active": True,
    })

    with patch("app.api.realtime_risk._portfolio_repo", repo):
        response = client.post("/api/realtime-analysis/risk/portfolio", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is False
    assert "已存在" in data["message"]
