"""风险预警推送合约：推送字段必须与 RiskAlert 模型对齐（历史 bug：字段名
错位导致第一条预警就 AttributeError，推送链路整体失效）。"""
import pandas as pd
import pytest

from app.services import websocket_push_service as wps
from app.services.websocket_push_service import WebSocketPushService


class _FakeAlert:
    """只模拟 _push_risk_alerts 用到的模型面。"""

    def __init__(self):
        # 别名逻辑直接读属性，模型上真实存在的字段都要有
        self.alert_message = "回撤超过阈值"
        self._dict = {
            "id": 7,
            "ts_code": "000001.SZ",
            "alert_type": "drawdown",
            "alert_level": "high",
            "alert_message": "回撤超过阈值",
            "risk_value": 0.12,
            "threshold_value": 0.10,
            "current_price": 9.9,
            "position_size": 1000.0,
            "portfolio_weight": 0.2,
            "is_active": True,
            "is_resolved": False,
            "created_at": "2026-08-29T10:00:00",
            "resolved_at": None,
        }

    def to_dict(self):
        return dict(self._dict)


def test_push_risk_alerts_sends_model_aligned_payload(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        wps.RiskAlert,
        "get_recent_alerts",
        classmethod(lambda cls, **kwargs: [_FakeAlert()]),
    )
    monkeypatch.setattr(wps, "broadcast_risk_alert", lambda payload: pushed.append(payload))

    service = WebSocketPushService.__new__(WebSocketPushService)
    service._push_risk_alerts()

    assert len(pushed) == 1, "推送不应因字段名错位而静默失败"
    payload = pushed[0]
    assert payload["alert_level"] == "high"
    assert payload["alert_message"] == "回撤超过阈值"
    assert payload["current_price"] == 9.9
    # 前端 websocket_management.html 直接读 alert.message，别名必须保留
    assert payload["message"] == "回撤超过阈值"
