from unittest.mock import patch

import pytest

from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository

pytestmark = pytest.mark.module_portfolio


def test_update_portfolio_position_endpoint_updates_supported_fields(app, tmp_path):
    client = app.test_client()

    payload = {
        "position_size": 1200,
        "avg_cost": 10.5,
        "current_price": 11.2,
        "sector": "银行",
        "stop_loss_price": 9.8,
        "take_profit_price": 12.6,
    }

    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    repo.upsert_position({
        "portfolio_id": "growth_a",
        "ts_code": "000001.SZ",
        "position_size": 1000.0,
        "avg_cost": 10.0,
        "current_price": 10.0,
        "market_value": 10000,
        "unrealized_pnl": 0,
        "is_active": True,
    })

    # 获取分配的 id
    positions = repo.list_positions("growth_a", active_only=False)
    position_id = positions[0]["id"]

    with patch("app.api.realtime_risk._portfolio_repo", repo):
        response = client.put(
            f"/api/realtime-analysis/risk/portfolio/growth_a/positions/{position_id}",
            json=payload,
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["position_size"] == 1200.0
    assert data["data"]["avg_cost"] == 10.5
    assert data["data"]["current_price"] == 11.2
    assert data["data"]["sector"] == "银行"
    assert data["data"]["market_value"] == 13440.0
    assert data["data"]["unrealized_pnl"] == pytest.approx(840.0)


def test_update_portfolio_position_endpoint_returns_not_found_when_missing(app, tmp_path):
    client = app.test_client()

    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

    with patch("app.api.realtime_risk._portfolio_repo", repo):
        response = client.put(
            "/api/realtime-analysis/risk/portfolio/growth_a/positions/9999",
            json={"position_size": 1200},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is False
    assert "不存在" in data["message"]
