from unittest.mock import patch

from app.services.websocket_push_service import WebSocketPushService


def test_push_portfolio_updates_skips_when_no_real_portfolios():
    service = WebSocketPushService()

    with patch.object(service, "_get_active_portfolio_ids", return_value=[]), \
         patch("app.services.websocket_push_service.broadcast_portfolio_update") as broadcast_update:
        service._push_portfolio_updates()

    broadcast_update.assert_not_called()


def test_push_portfolio_updates_uses_real_portfolio_ids():
    service = WebSocketPushService()

    with patch.object(service, "_get_active_portfolio_ids", return_value=["p1", "p2"]), \
         patch.object(service.risk_manager, "calculate_portfolio_risk", side_effect=lambda pid: {"portfolio_id": pid}), \
         patch("app.services.websocket_push_service.broadcast_portfolio_update") as broadcast_update:
        service._push_portfolio_updates()

    broadcasted_ids = [call.args[0] for call in broadcast_update.call_args_list]
    assert broadcasted_ids == ["p1", "p2"]
