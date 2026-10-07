"""预警推送服务测试：配置清洗、渠道投递（requests 打桩）、级别过滤、日志。"""

from __future__ import annotations

import json

import pytest

from app.services.alert_push_service import AlertPushService


@pytest.fixture()
def svc(tmp_path):
    return AlertPushService(data_dir=str(tmp_path))


def _record(level="warn", message="中证500：bear → bull"):
    return {
        "scan_date": "2026-10-06",
        "alerts": [{"type": "regime_flip", "level": level, "message": message}],
        "regime": [{"code": "000905.SH", "name": "中证500", "regime": "bull"}],
        "signals": {"stats": {"counts": {"squeeze": 3, "resonance": 1, "divergence": 0}}},
    }


class TestConfig:
    def test_default_config_disabled(self, svc):
        cfg = svc.get_config()
        assert cfg == {"enabled": False, "min_level": "info", "channels": []}

    def test_sanitize_drops_invalid_channels(self, svc):
        cfg = svc.update_config({
            "enabled": True,
            "min_level": "warn",
            "channels": [
                {"type": "serverchan", "send_key": "SCT123"},
                {"type": "webhook", "url": "https://example.com/hook"},
                {"type": "bogus", "url": "x"},          # 未知类型剔除
                {"type": "wecom_webhook", "url": ""},    # 空参数剔除
                "not-a-dict",
            ],
        })
        assert cfg["enabled"] is True
        assert cfg["min_level"] == "warn"
        assert [c["type"] for c in cfg["channels"]] == ["serverchan", "webhook"]

    def test_roundtrip_persisted(self, svc):
        svc.update_config({"enabled": True, "channels": [{"type": "serverchan", "send_key": "K"}]})
        cfg2 = AlertPushService(data_dir=svc.data_dir).get_config()
        assert cfg2["channels"] == [{"type": "serverchan", "send_key": "K"}]


class TestPush:
    def test_disabled_is_noop(self, svc, monkeypatch):
        called = []
        monkeypatch.setattr("app.services.alert_push_service.requests.post",
                            lambda *a, **k: called.append(a))
        assert svc.push_record(_record()) == []
        assert called == []

    def test_pushes_to_all_channels(self, svc, monkeypatch):
        svc.update_config({"enabled": True, "channels": [
            {"type": "serverchan", "send_key": "SCT1"},
            {"type": "webhook", "url": "https://example.com/hook"},
        ]})

        captured = {}

        class _Resp:
            def __init__(self, payload):
                self._payload = payload
                self.status_code = 200

            def json(self):
                return self._payload

        def fake_post(url, **kwargs):
            captured[url] = kwargs
            return _Resp({"code": 0} if "sctapi" in url else {"errcode": 0})

        monkeypatch.setattr("app.services.alert_push_service.requests.post", fake_post)
        results = svc.push_record(_record())
        assert all(r["ok"] for r in results)
        assert any("sctapi" in u for u in captured)
        hook = next(v for u, v in captured.items() if "example.com" in u)
        body = hook["json"]
        assert body["scan_date"] == "2026-10-06"
        assert "bear → bull" in body["text"]
        # 推送日志已落盘
        log = svc.list_log()
        assert len(log) == 1 and log[0]["scan_date"] == "2026-10-06"

    def test_min_level_warn_filters_info_only(self, svc, monkeypatch):
        svc.update_config({"enabled": True, "min_level": "warn",
                           "channels": [{"type": "webhook", "url": "https://x.com"}]})
        called = []
        monkeypatch.setattr("app.services.alert_push_service.requests.post",
                            lambda *a, **k: called.append(a))
        assert svc.push_record(_record(level="info")) == []
        assert called == []

    def test_http_error_reported_not_raised(self, svc, monkeypatch):
        svc.update_config({"enabled": True, "channels": [{"type": "webhook", "url": "https://x.com"}]})

        class _Resp:
            status_code = 500

            def json(self):
                raise ValueError("not json")

        monkeypatch.setattr("app.services.alert_push_service.requests.post", lambda *a, **k: _Resp())
        results = svc.push_record(_record())
        assert results[0]["ok"] is False
        assert "500" in results[0]["message"]

    def test_business_errcode_reported(self, svc, monkeypatch):
        svc.update_config({"enabled": True, "channels": [{"type": "dingtalk_webhook",
                                                         "url": "https://oapi.dingtalk.com/x"}]})

        class _Resp:
            status_code = 200

            def json(self):
                return {"errcode": 310000, "errmsg": "sign not match"}

        monkeypatch.setattr("app.services.alert_push_service.requests.post", lambda *a, **k: _Resp())
        results = svc.push_record(_record())
        assert results[0]["ok"] is False
        assert "sign not match" in results[0]["message"]

    def test_send_test_without_channels(self, svc):
        assert svc.send_test()["ok"] is False
