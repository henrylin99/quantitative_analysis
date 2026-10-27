"""策略守护 API 契约：登记/查询/删除/复活/历史。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.module_backtest


@pytest.fixture()
def isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield tmp_path


def test_guardian_api_crud(app, isolated_dir):
    client = app.test_client()

    resp = client.get("/api/strategy-guardian/strategies")
    assert resp.status_code == 200
    assert resp.get_json()["data"] == []

    resp = client.post("/api/strategy-guardian/strategies", json={
        "name": "共振信号-v1", "kind": "chip_signal",
        "params": {"resonance_winner_lo": 30.0}, "signal": "resonance",
    })
    assert resp.status_code == 200
    sid = resp.get_json()["data"]["id"]
    assert sid.startswith("chip_signal-")

    # 缺 name → 400；非法 kind → 400
    assert client.post("/api/strategy-guardian/strategies", json={}).status_code == 400
    assert client.post("/api/strategy-guardian/strategies", json={
        "name": "x", "kind": "magic"}).status_code == 400

    assert client.get("/api/strategy-guardian/history").get_json()["data"] == []
    # 非退役策略 resume → 404（仅退役策略可复活）
    assert client.post(f"/api/strategy-guardian/strategies/{sid}/resume").status_code == 404

    resp = client.delete(f"/api/strategy-guardian/strategies/{sid}")
    assert resp.status_code == 200
    assert client.delete(f"/api/strategy-guardian/strategies/{sid}").status_code == 404
