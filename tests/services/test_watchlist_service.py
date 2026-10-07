"""自选股服务测试：CRUD、清洗、去重、价格提醒触发与去重。"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.watchlist_service import WatchlistAlertService, WatchlistService


@pytest.fixture()
def svc(tmp_path):
    return WatchlistService(data_dir=str(tmp_path))


@pytest.fixture()
def alert_svc(tmp_path, monkeypatch):
    """带合成行情的价格提醒服务。"""
    svc = WatchlistAlertService(data_dir=str(tmp_path))
    daily = pd.DataFrame([
        {"ts_code": "600519.SH", "trade_date": "2026-10-05", "close": 1500.0},
        {"ts_code": "600519.SH", "trade_date": "2026-10-06", "close": 980.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-10-06", "close": 12.5},
    ])

    class _FakeReader:
        def get_daily(self, ts_codes=None, start_date=None, end_date=None):
            return daily.copy()

    import app.services.data_reader as dr_mod
    monkeypatch.setattr(dr_mod.ParquetDataReader, "get_daily",
                        lambda self, ts_codes=None, start_date=None, end_date=None: daily.copy())
    return svc


class TestCrud:
    def test_add_normalizes_and_dedupes(self, svc):
        svc.add_item("600519", group="白酒")
        item = svc.add_item("600519.SH")  # 重复添加返回已有
        items = svc.list_items()
        assert len(items) == 1
        assert items[0]["ts_code"] == "600519.SH"
        assert items[0]["group"] == "白酒"
        assert item["ts_code"] == "600519.SH"

    def test_sanitize_rules(self, svc):
        items = svc.replace_items([
            {"ts_code": "000001", "group": "", "alert_high": "15.5"},
            {"ts_code": "", "group": "x"},              # 无代码剔除
            {"ts_code": "600000.SH", "alert_high": -3},  # 非法提醒价置空
            {"ts_code": "600000.SH", "note": "dup"},     # 代码重复取第一个
        ])
        assert len(items) == 2
        first = items[0]
        assert first["ts_code"] == "000001.SZ"
        assert first["group"] == "默认"
        assert first["alert_high"] == 15.5
        assert items[1]["alert_high"] is None
        assert items[1]["note"] == ""

    def test_update_and_remove(self, svc):
        svc.add_item("600519.SH")
        updated = svc.update_item("600519.SH", {"note": "高端白酒", "alert_low": 1400})
        assert updated["note"] == "高端白酒"
        assert updated["alert_low"] == 1400.0
        assert updated["group"] == "默认"  # 未动字段保留
        assert svc.remove_item("600519.SH") is True
        assert svc.remove_item("600519.SH") is False
        assert svc.list_items() == []

    def test_persisted_across_instances(self, tmp_path, svc):
        svc.add_item("600519.SH")
        other = WatchlistService(data_dir=str(tmp_path))
        assert [x["ts_code"] for x in other.list_items()] == ["600519.SH"]


class TestAlerts:
    def _setup(self, svc):
        svc.replace_items([
            {"ts_code": "600519.SH", "alert_low": 1000},
            {"ts_code": "000001.SZ", "alert_high": 12},
            {"ts_code": "300750.SZ", "alert_high": 999},  # 无行情 → 跳过
        ])

    def test_trigger_and_dedupe(self, tmp_path, alert_svc):
        self._setup(WatchlistService(data_dir=str(tmp_path)))
        result = alert_svc.check()
        kinds = {(a["ts_code"], a["kind"]) for a in result["triggered"]}
        assert kinds == {("600519.SH", "below"), ("000001.SZ", "above")}
        assert result["triggered"][0]["message"]

        # 再跑一轮：同票同方向同收盘日去重
        again = alert_svc.check()
        assert again["triggered"] == []

    def test_no_thresholds_noop(self, tmp_path, alert_svc):
        WatchlistService(data_dir=str(tmp_path)).add_item("600519.SH")
        assert alert_svc.check() == {"checked": 0, "triggered": []}

    def test_alerts_persisted(self, tmp_path, alert_svc):
        self._setup(WatchlistService(data_dir=str(tmp_path)))
        alert_svc.check()
        other = WatchlistAlertService(data_dir=str(tmp_path))
        assert len(other.list_alerts()) == 2
