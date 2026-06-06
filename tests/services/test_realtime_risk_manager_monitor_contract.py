from unittest.mock import patch

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
