from unittest.mock import patch

import pytest

from app.services.realtime_risk_manager import RealtimeRiskManager


def test_monitor_position_risk_updates_market_data():
    manager = RealtimeRiskManager()

    positions = [{
        "ts_code": "000001.SZ",
        "position_size": 1000.0,
        "avg_cost": 10.0,
        "current_price": 10.0,
        "market_value": 10000.0,
        "unrealized_pnl": 0.0,
        "weight": 100.0,
        "sector": "银行",
        "var_1d": 0.01,
        "var_5d": 0.02,
        "beta": 1.0,
        "volatility": 0.2,
        "is_active": True,
    }]

    with patch("app.services.realtime_risk_manager._portfolio_repo") as repo:
        repo.list_positions.return_value = positions
        repo.calculate_metrics.return_value = {"total_market_value": 10000.0}

        with patch.object(manager, "_get_current_price", return_value=11.0):
            result = manager.monitor_position_risk("growth_a")

    assert result["success"] is True
    # upsert_position 应被调用以持久化更新的价格
    assert repo.upsert_position.call_count == 1
    saved = repo.upsert_position.call_args[0][0]
    assert saved["current_price"] == 11.0
    assert saved["market_value"] == 11000.0
    assert saved["unrealized_pnl"] == 1000.0


def test_monitor_position_risk_computes_weights_after_price_refresh():
    """Weight 应基于刷新后的市值计算，而非刷新前。"""
    manager = RealtimeRiskManager()

    positions = [
        {
            "ts_code": "000001.SZ",
            "position_size": 1000.0,
            "avg_cost": 10.0,
            "current_price": 10.0,
            "market_value": 10000.0,
            "unrealized_pnl": 0.0,
            "weight": None,
            "is_active": True,
        },
        {
            "ts_code": "000002.SZ",
            "position_size": 500.0,
            "avg_cost": 20.0,
            "current_price": 20.0,
            "market_value": 10000.0,
            "unrealized_pnl": 0.0,
            "weight": None,
            "is_active": True,
        },
    ]

    def fake_get_price(ts_code):
        return 12.0 if ts_code == "000001.SZ" else 18.0

    with patch("app.services.realtime_risk_manager._portfolio_repo") as repo:
        repo.list_positions.return_value = positions
        repo.calculate_metrics.return_value = {"total_market_value": 21000.0}

        with patch.object(manager, "_get_current_price", side_effect=fake_get_price):
            result = manager.monitor_position_risk("growth_a")

    assert result["success"] is True
    # 000001: 1000*12=12000, 000002: 500*18=9000, total=21000
    # weight: 12000/21000*100 ≈ 57.14, 9000/21000*100 ≈ 42.86
    assert positions[0]["weight"] == pytest.approx(57.142857, rel=1e-3)
    assert positions[1]["weight"] == pytest.approx(42.857142, rel=1e-3)


def test_create_risk_alert_uses_model_creator():
    from types import SimpleNamespace

    manager = RealtimeRiskManager()

    alert = SimpleNamespace(
        to_dict=lambda: {
            "id": 9,
            "ts_code": "000001.SZ",
            "alert_type": "stop_loss_triggered",
            "alert_level": "high",
        }
    )

    positions = [{"ts_code": "000001.SZ", "position_size": 1000, "weight": 25.0}]

    with patch("app.services.realtime_risk_manager.RiskAlert.get_existing_active_alert", return_value=None), \
         patch("app.services.realtime_risk_manager._portfolio_repo") as repo, \
         patch.object(manager, "_get_current_price", return_value=10.2), \
         patch("app.services.realtime_risk_manager.RiskAlert.create_alert", return_value=alert) as create_alert:
        repo.list_portfolio_ids.return_value = ["growth_a"]
        repo.list_positions.return_value = positions

        result = manager.create_risk_alert(
            ts_code="000001.SZ",
            alert_type="stop_loss_triggered",
            alert_level="high",
            alert_message="触发止损",
        )

    assert result["success"] is True
    assert result["data"]["ts_code"] == "000001.SZ"
    assert create_alert.call_count == 1
