"""Paper trading 模拟盘测试：挂单生成、次日开盘成交、涨跌停/停牌、盯市与对齐报告。"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.paper_trading_service import PaperTradingService


class _StubReader:
    """行情桩：两日两票 + 涨停票 + 停牌票。"""

    def __init__(self, mode: str = "normal"):
        self.mode = mode

    def get_trade_dates(self):
        return ["2026-10-10", "2026-10-13", "2026-10-14", "2026-10-15"]

    def get_stock_basic(self):
        return pd.DataFrame([{"ts_code": "600001.SH", "name": "甲"},
                             {"ts_code": "600002.SH", "name": "乙"}])

    def get_daily(self, ts_codes=None, start_date=None, end_date=None):
        d = str(end_date).replace("-", "")
        rows = []
        for code in (ts_codes or []):
            if self.mode == "suspend" and code == "600002.SH" and d == "20261013":
                continue  # 停牌
            if self.mode == "limit_up" and code == "600002.SH":
                rows.append({"ts_code": code, "open": 11.0, "close": 11.0,
                             "pre_close": 10.0, "pct_chg": 10.0})
                continue
            base = {"600001.SH": 10.0, "600002.SH": 10.0}.get(code, 10.0)
            rows.append({"ts_code": code, "open": base, "close": base,
                         "pre_close": base, "pct_chg": 0.0})
        return pd.DataFrame(rows)


def _scan(codes=("600001.SH",), date="2026-10-10"):
    rows = [{"ts_code": c, "close": 10.0} for c in codes]
    return {"stats": {"scan_date": date}, "resonance": rows, "squeeze": [], "divergence": []}


@pytest.fixture()
def service(tmp_path):
    return PaperTradingService(data_dir=str(tmp_path), data_reader=_StubReader())


def test_generate_orders_buy_and_sell(service):
    service.reset(initial_cash=200_000, top_n=2)
    # 先持有一只不在新目标内的票
    service.generate_orders(scan=_scan(("600001.SH",)), force=True)
    service.settle(exec_date="20261013")
    assert "600001.SH" in service._load()["positions"]

    result = service.generate_orders(scan=_scan(("600002.SH",)), force=True)
    sides = {o["ts_code"]: o["side"] for o in result["orders"]}
    assert sides == {"600001.SH": "sell", "600002.SH": "buy"}


def test_settle_fills_at_open_with_costs(service):
    service.reset(initial_cash=200_000, top_n=1)
    service.generate_orders(scan=_scan(("600001.SH",)))
    result = service.settle(exec_date="20261013")
    assert result["filled"] == 1
    state = service._load()
    pos = state["positions"]["600001.SH"]
    # target_value=200000/1，预算含成本向下取整手 → 19900股；成本计入 avg_cost
    assert pos["qty"] == 19900
    assert pos["avg_cost"] > 10.0
    trade = state["trades"][0]
    assert trade["side"] == "buy" and trade["price_gap"] == 0.0
    assert trade["costs"]["total_cost"] > 0
    assert state["cash"] < 200_000
    # 订单关闭
    assert all(o["status"] != "pending" for o in state["pending_orders"])


def test_t_plus_1_orders_not_settled_same_day(service):
    service.reset(initial_cash=200_000, top_n=1)
    service.generate_orders(scan=_scan(("600001.SH",)))
    result = service.settle(exec_date="20261010")  # 同一交易日不成交
    assert result["filled"] == 0
    assert service._load()["positions"] == {}


def test_limit_up_open_blocks_buy(service):
    service.reset(initial_cash=200_000, top_n=1)
    lim = PaperTradingService(data_dir=service.data_dir, data_reader=_StubReader("limit_up"))
    lim._save(service._load())
    lim.generate_orders(scan=_scan(("600002.SH",)))
    result = lim.settle(exec_date="20261013")
    assert result["filled"] == 0
    # 3 个交易日重试后过期
    lim.settle(exec_date="20261014")
    r3 = lim.settle(exec_date="20261015")
    assert r3["expired"] == 1
    state = lim._load()
    assert state["pending_orders"][0]["status"] == "expired"
    assert state["stats"]["expired"] == 1


def test_suspension_keeps_order_pending(service):
    service.reset(initial_cash=200_000, top_n=1)
    sus = PaperTradingService(data_dir=service.data_dir, data_reader=_StubReader("suspend"))
    sus._save(service._load())
    sus.generate_orders(scan=_scan(("600002.SH",)))
    sus.settle(exec_date="20261013")
    state = sus._load()
    assert state["pending_orders"][0]["status"] == "pending"
    assert state["positions"] == {}


def test_mark_and_alignment(service):
    service.reset(initial_cash=200_000, top_n=1)
    service.generate_orders(scan=_scan(("600001.SH",)))
    service.settle(exec_date="20261013")
    service.mark(date="20261013")
    state = service._load()
    assert state["nav_history"][-1]["date"] == "20261013"
    assert state["nav_history"][-1]["basket_ret"] == 0.0
    service.mark(date="20261013")  # 重复盯市幂等
    assert len(state["nav_history"]) == service._load()["nav_history"].__len__()

    report = service.alignment_report()
    assert report["n_days"] == 1
    assert report["attribution"]["n_trades"] == 1
    assert report["attribution"]["cost_drag_pct"] > 0
    assert "跟踪误差" in report["note"] or "对齐基准" in report["note"]


def test_status_positions_and_pnl(service):
    service.reset(initial_cash=200_000, top_n=1)
    service.generate_orders(scan=_scan(("600001.SH",)))
    service.settle(exec_date="20261013")
    st = service.status()
    assert st["positions"][0]["ts_code"] == "600001.SH"
    assert st["positions"][0]["pnl"] < 0  # 成本拖累
    assert st["stats"]["filled"] == 1
