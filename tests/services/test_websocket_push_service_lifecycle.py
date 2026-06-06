"""WebSocket推送服务生命周期与合约测试"""
from unittest.mock import patch

import pandas as pd

from app.services.websocket_push_service import WebSocketPushService


# ---------- lifecycle ----------

def test_stop_push_service_sets_is_running_false():
    """stop 应将 is_running 置 False"""
    service = WebSocketPushService()
    service.is_running = True
    service.stop_push_service()
    assert service.is_running is False


def test_start_push_service_refuses_double_start():
    """运行中再次 start 应 warning 并跳过"""
    service = WebSocketPushService()
    service.is_running = True
    with patch("app.extensions.socketio") as mock_sio:
        service.start_push_service()
        mock_sio.start_background_task.assert_not_called()


# ---------- _push_market_data ----------

def test_push_market_data_uses_available_stocks_and_fallback_period():
    """应使用 get_available_minute_stocks + get_minute_latest_data"""
    service = WebSocketPushService()

    fake_df = pd.DataFrame([
        {"datetime": "2026-01-01 10:00", "open": 10.0, "high": 10.5,
         "low": 9.8, "close": 10.2, "volume": 1000, "amount": 10000},
        {"datetime": "2026-01-01 09:59", "open": 10.1, "high": 10.3,
         "low": 9.9, "close": 10.0, "volume": 900, "amount": 9000},
    ])

    with patch.object(service.data_manager, "get_available_minute_stocks",
                      return_value=["000001.SZ"]), \
         patch.object(service.data_manager, "get_minute_latest_data",
                      return_value=fake_df), \
         patch("app.services.websocket_push_service.broadcast_market_data") as bc:

        service._push_market_data()

    assert bc.call_count == 2  # per-stock + 'all'
    # First call: specific stock
    assert bc.call_args_list[0].args[0] == "000001.SZ"
    # Second call: broadcast to 'all'
    assert bc.call_args_list[1].args[0] == "all"


def test_push_market_data_skips_empty_data():
    """get_minute_latest_data 返回空 DataFrame 时跳过该股票"""
    service = WebSocketPushService()

    with patch.object(service.data_manager, "get_available_minute_stocks",
                      return_value=["000001.SZ"]), \
         patch.object(service.data_manager, "get_minute_latest_data",
                      return_value=pd.DataFrame()), \
         patch("app.services.websocket_push_service.broadcast_market_data") as bc:

        service._push_market_data()

    bc.assert_not_called()


# ---------- _push_monitor_data ----------

def test_push_monitor_data_unpacks_anomaly_list():
    """detect_anomalies 返回的包装 dict 应解包为 anomalies 列表"""
    service = WebSocketPushService()

    anomaly_response = {
        "success": True,
        "data": {
            "anomalies": [{"ts_code": "000001.SZ", "anomaly_types": ["急涨"]}],
            "total_count": 1,
        },
    }

    with patch.object(service.data_manager, "get_market_overview",
                      return_value={"total_stocks": 100}), \
         patch.object(service.monitor_service, "detect_anomalies",
                      return_value=anomaly_response), \
         patch.object(service.monitor_service, "get_market_sentiment",
                      return_value={"sentiment": "neutral"}), \
         patch("app.services.websocket_push_service.broadcast_monitor_data") as bc:

        service._push_monitor_data()

    payload = bc.call_args.args[0]
    # top_movers 和 anomalies 都应该是 list，不是包装 dict
    assert isinstance(payload["top_movers"], list)
    assert isinstance(payload["anomalies"], list)
    assert payload["top_movers"][0]["ts_code"] == "000001.SZ"


def test_push_monitor_data_handles_detect_failure():
    """detect_anomalies 返回 success=False 时应降级为空列表"""
    service = WebSocketPushService()

    with patch.object(service.data_manager, "get_market_overview",
                      return_value={}), \
         patch.object(service.monitor_service, "detect_anomalies",
                      return_value={"success": False, "message": "error"}), \
         patch.object(service.monitor_service, "get_market_sentiment",
                      return_value={}), \
         patch("app.services.websocket_push_service.broadcast_monitor_data") as bc:

        service._push_monitor_data()

    payload = bc.call_args.args[0]
    assert payload["top_movers"] == []
    assert payload["anomalies"] == []


# ---------- _calculate_change_pct ----------

def test_calculate_change_pct_with_two_rows():
    service = WebSocketPushService()
    df = pd.DataFrame([
        {"close": 11.0},
        {"close": 10.0},
    ])
    pct = service._calculate_change_pct(df)
    assert pct == 10.0


def test_calculate_change_pct_single_row_fallback():
    service = WebSocketPushService()
    df = pd.DataFrame([
        {"close": 11.0, "open": 10.0},
    ])
    pct = service._calculate_change_pct(df)
    assert pct == 10.0


def test_calculate_change_pct_empty_df():
    service = WebSocketPushService()
    pct = service._calculate_change_pct(pd.DataFrame())
    assert pct == 0.0
