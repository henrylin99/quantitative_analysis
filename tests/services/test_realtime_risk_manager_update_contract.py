from unittest.mock import patch

from app.services.realtime_risk_manager import RealtimeRiskManager


def test_manage_stop_loss_take_profit_updates_positions():
    manager = RealtimeRiskManager()

    positions = [{
        "ts_code": "000001.SZ",
        "position_size": 1000.0,
        "avg_cost": 10.0,
        "current_price": 10.0,
        "market_value": 10000.0,
        "unrealized_pnl": 0.0,
        "stop_loss_price": None,
        "take_profit_price": None,
        "weight": 100.0,
        "is_active": True,
    }]

    with patch("app.services.realtime_risk_manager._portfolio_repo") as repo:
        repo.list_positions.return_value = positions
        result = manager.manage_stop_loss_take_profit("growth_a")

    assert result["success"] is True
    # upsert_position 应被调用以持久化止损止盈价格
    assert repo.upsert_position.call_count == 1
    saved = repo.upsert_position.call_args[0][0]
    assert saved["stop_loss_price"] == 9.0  # 10.0 * (1 - 0.10)
    assert saved["take_profit_price"] == 12.0  # 10.0 * (1 + 0.20)
