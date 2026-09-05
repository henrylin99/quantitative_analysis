"""TickFlow 轻量客户端合约测试：认证头、权限错误、档位探测。"""

import pytest

from app.utils.data_sources.tickflow_client import TickflowClient, TickflowError


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(payload={"data": {}})


def _ok(payload):
    return FakeResponse(payload={"data": payload})


def test_missing_key_raises_no_key(monkeypatch):
    monkeypatch.delenv("TICKFLOW_API_KEY", raising=False)
    client = TickflowClient(api_key="")
    with pytest.raises(TickflowError) as exc:
        client.klines("600000.SH")
    assert "TICKFLOW_API_KEY" in str(exc.value)


def test_klines_uses_x_api_key_header_and_drops_none():
    client = TickflowClient(api_key="tk-test")
    client._session = FakeSession([_ok({"close": [9.2]})])
    data = client.klines("600000.SH", count=1)
    assert data == {"close": [9.2]}
    call = client._session.calls[0]
    assert call["headers"] == {"x-api-key": "tk-test"}
    assert call["params"] == {"symbol": "600000.SH", "period": "1d", "count": 1, "adjust": "none"}


def test_permission_denied_error_flagged():
    client = TickflowClient(api_key="tk-test")
    client._session = FakeSession([
        FakeResponse(payload={"code": "NO_KLINE_PERMISSION", "message": "无分钟K线查询权限"},
                     status_code=403),
    ])
    with pytest.raises(TickflowError) as exc:
        client.klines("600000.SH", period="1m")
    assert exc.value.is_permission_denied


def test_quotes_accepts_list_payload():
    client = TickflowClient(api_key="tk-test")
    client._session = FakeSession([_ok([{"symbol": "600000.SH", "last_price": 9.28}])])
    assert client.quotes(["600000.SH"])[0]["last_price"] == 9.28


def test_quotes_accepts_wrapped_payload():
    client = TickflowClient(api_key="tk-test")
    client._session = FakeSession([_ok({"quotes": [{"symbol": "600000.SH"}]})])
    assert client.quotes(["600000.SH"]) == [{"symbol": "600000.SH"}]


def test_detect_tier_none_when_klines_denied():
    client = TickflowClient(api_key="tk-bad")
    client._session = FakeSession([
        FakeResponse(payload={"code": "NO_KLINE_PERMISSION", "message": "denied"}, status_code=403),
    ])
    assert client.detect_tier() == "none"


def test_detect_tier_free_when_ex_factors_denied():
    client = TickflowClient(api_key="tk-free")
    client._session = FakeSession([
        _ok({"close": [9.2]}),
        FakeResponse(payload={"code": "NO_EX_FACTORS_PERMISSION", "message": "denied"},
                     status_code=403),
    ])
    assert client.detect_tier() == "free"


def test_detect_tier_paid_when_ex_factors_ok():
    client = TickflowClient(api_key="tk-paid")
    client._session = FakeSession([
        _ok({"close": [9.2]}),
        _ok({"600000.SH": [{"ex_factor": 1.0, "timestamp": 1}]}),
    ])
    assert client.detect_tier() == "paid"


def test_detect_tier_none_without_key(monkeypatch):
    monkeypatch.delenv("TICKFLOW_API_KEY", raising=False)
    assert TickflowClient(api_key="").detect_tier() == "none"
