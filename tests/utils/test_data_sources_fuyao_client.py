"""扶摇 REST 客户端合约测试：信封解包、错误码、节流、分页、dump 下载。"""

import time

import pytest

from app.utils.data_sources.fuyao_client import (
    FuyaoClient,
    FuyaoError,
    beijing_ms_to_ymd,
    release_of,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text="", chunks=()):
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self._chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)


class FakeSession:
    """按序回放响应，并记录每次调用的 url/headers/params。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None, stream=False, **kwargs):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}, "stream": stream})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(payload={"code": 0, "message": "ok", "data": {}})

    def stream(self, method, url, timeout=None):
        self.calls.append({"url": url, "headers": {}, "params": {}, "stream": True})
        return self.responses.pop(0)


@pytest.fixture
def client():
    return FuyaoClient(api_key="sk-test", throttle_seconds=0)


# ---- 时间口径 ----

def test_beijing_ms_to_ymd_uses_beijing_midnight():
    # 1751385600000 = 2025-07-01 16:00 UTC = 北京时间 2025-07-02 零点
    assert beijing_ms_to_ymd(1751385600000) == "20250702"


def test_beijing_ms_to_ymd_handles_none_and_nan():
    assert beijing_ms_to_ymd(None) is None
    assert beijing_ms_to_ymd(float("nan")) is None


def test_release_of_extracts_date_from_url():
    url = "https://o.thsi.cn/x/releases/20260904/a.parquet?sig=abc"
    assert release_of(url) == "20260904"
    assert release_of("https://no-release-path/x.parquet") is None


# ---- 信封与错误 ----

def test_missing_key_raises_no_key(monkeypatch):
    monkeypatch.delenv("FUYAO_API_KEY", raising=False)
    client = FuyaoClient(api_key="", throttle_seconds=0)
    with pytest.raises(FuyaoError) as exc:
        client.trading_days()
    assert "FUYAO_API_KEY" in str(exc.value)


def test_error_code_raises_fuyao_error(client):
    client._session = FakeSession([FakeResponse(payload={"code": 1002, "message": "invalid"})])
    with pytest.raises(FuyaoError) as exc:
        client.trading_days()
    assert exc.value.code == 1002
    assert not exc.value.is_rate_limited


def test_rate_limit_code_flagged(client):
    client._session = FakeSession([FakeResponse(payload={"code": 4001, "message": "rate"})])
    with pytest.raises(FuyaoError) as exc:
        client.trading_days()
    assert exc.value.is_rate_limited


def test_http_error_raises(client):
    client._session = FakeSession([FakeResponse(status_code=500, text="boom")])
    with pytest.raises(FuyaoError):
        client.trading_days()


def test_none_params_are_dropped(client):
    client._session = FakeSession()
    client.historical_kline("600000.SH", start_ms=123, end_ms=None)
    params = client._session.calls[0]["params"]
    assert params["thscode"] == "600000.SH"
    assert params["start"] == 123
    assert "end" not in params


# ---- 节流 ----

def test_throttle_enforces_min_interval():
    client = FuyaoClient(api_key="sk-test", throttle_seconds=0.05)
    client._session = FakeSession()
    start = time.monotonic()
    client.trading_days()
    client.trading_days()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05


# ---- 快照分页 ----

def test_snapshot_all_paginates_until_total_reached(client):
    page1 = {"timestamp": 123, "total": 3, "item": [{"thscode": f"00000{i}.SZ"} for i in (1, 2)]}
    page2 = {"timestamp": 123, "total": 3, "item": [{"thscode": "000003.SZ"}]}
    client._session = FakeSession([FakeResponse(payload={"code": 0, "message": "ok", "data": page1}),
                                   FakeResponse(payload={"code": 0, "message": "ok", "data": page2})])
    rows, ts = client.snapshot_all()
    assert len(rows) == 3
    assert ts == 123
    assert client._session.calls[0]["params"] == {"limit": 6000, "offset": 0}
    assert client._session.calls[1]["params"] == {"limit": 6000, "offset": 2}


def test_price_snapshot_batch_limits_to_100(client):
    client._session = FakeSession()
    client.price_snapshot_batch([f"{i:06d}.SZ" for i in range(150)])
    thscodes = client._session.calls[0]["params"]["thscodes"].split(",")
    assert len(thscodes) == 100
    assert "limit" not in client._session.calls[0]["params"]


def test_index_snapshot_joins_codes(client):
    client._session = FakeSession()
    client.index_snapshot(["000001.SH", "399001.SZ"])
    assert client._session.calls[0]["params"] == {"thscodes": "000001.SH,399001.SZ"}


# ---- dump 下载 ----

def test_download_dump_uses_presigned_url_without_api_key(client, tmp_path):
    presigned = "https://oss.example.com/x/releases/20260904/k.parquet?sig=1"
    client._session = FakeSession([
        FakeResponse(payload={"code": 0, "message": "ok",
                              "data": {"presigned_url": presigned}}),
        FakeResponse(chunks=[b"parquet", b"-bytes"]),
    ])
    dest = tmp_path / "cache" / "k__20260904.parquet"
    result = client.download_dump("daily-k-10d", dest)

    assert result == dest
    assert dest.read_bytes() == b"parquet-bytes"
    download_call = client._session.calls[1]
    assert download_call["url"] == presigned
    assert "X-api-key" not in download_call["headers"]
    assert not list(tmp_path.rglob("*.part.*"))  # 临时文件已清理


def test_download_dump_missing_url_raises(client, tmp_path):
    client._session = FakeSession([
        FakeResponse(payload={"code": 0, "message": "ok", "data": {}}),
    ])
    with pytest.raises(FuyaoError):
        client.download_dump("daily-k", tmp_path / "x.parquet")


# ---- 涨跌停特色数据 / 同花顺指数 ----

def test_limit_up_pool_passes_date_ms_and_paging(client):
    client._session = FakeSession([
        FakeResponse(payload={"code": 0, "message": "ok", "data": {
            "pagination": {"total": 1, "page": 2, "size": 50},
            "item": [{"thscode": "605577.SH", "continue_day_cnt": 5}],
        }}),
    ])
    data = client.limit_up_pool(date_ms=1788451200000, page=2, size=50)
    call = client._session.calls[0]
    assert call["url"].endswith("/api/a-share/special-data/limit-up-pool")
    assert call["params"]["date_ms"] == 1788451200000
    assert call["params"]["sort_field"] == "continue_day_cnt"
    assert data["item"][0]["continue_day_cnt"] == 5


def test_limit_up_ladder_returns_matrix(client):
    boards = {"two_board": [{"thscode": "600108.SH"}], "seven_over": []}
    client._session = FakeSession([
        FakeResponse(payload={"code": 0, "message": "ok",
                              "data": {"item": [{"date": "2026-09-04", "boards": boards}]}}),
    ])
    data = client.limit_up_ladder()
    assert data["item"][0]["boards"]["two_board"][0]["thscode"] == "600108.SH"


def test_ths_index_catalog_and_constituents(client):
    client._session = FakeSession([
        FakeResponse(payload={"code": 0, "message": "ok",
                              "data": {"item": [{"thscode": "881101.TI", "name": "种植业与林业"}]}}),
        FakeResponse(payload={"code": 0, "message": "ok",
                              "data": {"item": [{"thscode": "000998.SZ", "name": "隆平高科"}]}}),
    ])
    catalog = client.ths_index_catalog(tag="industry")
    constituents = client.ths_index_constituents("881101.TI")
    assert client._session.calls[0]["params"] == {"tag": "industry"}
    assert client._session.calls[1]["params"] == {"thscode": "881101.TI"}
    assert catalog[0]["name"] == "种植业与林业"
    assert constituents[0]["thscode"] == "000998.SZ"
