"""每日预警服务测试：记录落盘、同日去重、预警派生规则。"""

from __future__ import annotations

import json

import pytest

from app.services.daily_alert_service import DailyAlertService


@pytest.fixture
def svc(tmp_path):
    return DailyAlertService(data_dir=str(tmp_path))


def _snapshot(regime=None, codes=None, top="银行"):
    return {
        "regime": regime or [],
        "signals": {"stats": {}, "codes": codes or {}},
        "rotation": {"top": [{"industry": top, "total_score": 1.0}], "bottom": []},
        "anomaly": {"report_year": "2025", "total_flagged": 100},
    }


def test_first_scan_creates_baseline(svc):
    record = svc.run_scan()
    # 扫描到的数据源均为空（tmp 目录下无数据）→ 各快照为空但记录存在
    assert record["scan_date"]
    assert any(a["type"] == "init" for a in record["alerts"])
    assert svc.list_records()[0]["scan_date"] == record["scan_date"]


def test_same_day_dedup_and_force_overwrite(svc, monkeypatch):
    calls = {"n": 0}

    def fake_collect(self):
        calls["n"] += 1
        return _snapshot()

    monkeypatch.setattr(DailyAlertService, "_collect", fake_collect)
    svc.run_scan()
    svc.run_scan()  # 同日不重复扫描
    assert calls["n"] == 1
    svc.run_scan(force=True)
    assert calls["n"] == 2
    records = svc.list_records()
    assert len(records) == 1  # force 覆盖而非追加


def test_regime_flip_alert(svc, monkeypatch):
    snapshots = iter([
        _snapshot(regime=[{"code": "399300.SZ", "name": "沪深300", "regime": "震荡"}]),
        _snapshot(regime=[{"code": "399300.SZ", "name": "沪深300", "regime": "空头"}]),
    ])
    monkeypatch.setattr(DailyAlertService, "_collect", lambda self: next(snapshots))

    # 不同 scan_date： monkeypatch datetime 不便，直接构造两条历史记录再派生
    svc.run_scan()
    records = svc.list_records()
    records[0]["scan_date"] = "2026-10-05"
    with open(svc._file_path, "w", encoding="utf-8") as f:
        json.dump({"records": records}, f, ensure_ascii=False)

    alert = svc.run_scan(force=True)
    flips = [a for a in alert["alerts"] if a["type"] == "regime_flip"]
    assert len(flips) == 1
    assert "震荡 → 空头" in flips[0]["message"]


def test_new_signal_alert(svc, monkeypatch):
    snapshots = iter([
        _snapshot(codes={"squeeze": ["000001.SZ"]}),
        _snapshot(codes={"squeeze": ["000001.SZ", "600000.SH", "600519.SH"]}),
    ])
    monkeypatch.setattr(DailyAlertService, "_collect", lambda self: next(snapshots))
    svc.run_scan()
    records = svc.list_records()
    records[0]["scan_date"] = "2026-10-05"
    with open(svc._file_path, "w", encoding="utf-8") as f:
        json.dump({"records": records}, f, ensure_ascii=False)

    alert = svc.run_scan(force=True)
    new_alerts = [a for a in alert["alerts"] if a["type"] == "new_squeeze"]
    assert len(new_alerts) == 1
    assert "新增 2 只" in new_alerts[0]["message"]
