"""行业轮动服务测试：合成数据验证评分结构与行业聚合口径。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.industry_rotation_service import IndustryRotationService


class _FakeReader:
    def __init__(self, basic, daily, flow, dbasic):
        self._basic, self._daily, self._flow, self._dbasic = basic, daily, flow, dbasic

    def get_stock_basic(self):
        return self._basic.copy()

    def get_daily(self, ts_codes=None, start_date=None, end_date=None):
        return self._daily.copy()

    def get_moneyflow(self, ts_codes=None, start_date=None, end_date=None):
        return self._flow.copy()

    def get_daily_basic(self, ts_codes=None, start_date=None, end_date=None):
        return self._dbasic.copy()


def _fixtures(n_days=80, n_per_industry=10):
    dates = pd.bdate_range("2026-06-01", periods=n_days)
    # 银行温和上涨；半导体下跌 → 银行动量分应更高
    basic = pd.DataFrame({
        "ts_code": [f"{p}{i:06d}.{s}" for p, s in (("000", "SZ"), ("600", "SH"))
                    for i in range(1, n_per_industry + 1)],
        "industry": ["银行"] * n_per_industry + ["半导体"] * n_per_industry,
    })
    rows = []
    for code, ind in zip(basic["ts_code"], basic["industry"]):
        drift = 0.002 if ind == "银行" else -0.002
        price = 10.0
        for d in dates:
            price *= 1 + drift
            rows.append({"ts_code": code, "trade_date": d, "open": price,
                         "close": price, "vol": 100.0})
    daily = pd.DataFrame(rows)
    flow_rows = []
    db_rows = []
    for code, ind in zip(basic["ts_code"], basic["industry"]):
        net = 100.0 if ind == "银行" else -100.0
        pe = 10.0 if ind == "银行" else 80.0
        for d in dates:
            flow_rows.append({"ts_code": code, "trade_date": d,
                              "buy_lg_amount": max(net, 0), "buy_elg_amount": max(net, 0),
                              "sell_lg_amount": max(-net, 0), "sell_elg_amount": max(-net, 0)})
            db_rows.append({"ts_code": code, "trade_date": d, "pe_ttm": pe})
    flow = pd.DataFrame(flow_rows)
    dbasic = pd.DataFrame(db_rows)
    return basic, daily, flow, dbasic


def test_rotation_ranks_momentum_and_flow():
    basic, daily, flow, dbasic = _fixtures()
    reader = _FakeReader(basic, daily, flow, dbasic)
    result = IndustryRotationService(reader).run(months=12, force_refresh=True)

    assert "error" not in result
    assert result["meta"]["n_industries"] == 2
    rows = {r["industry"]: r for r in result["rows"]}
    # 银行：动量正、资金净流入、PE 低 → 总分应高于半导体
    assert rows["银行"]["rank"] == 1
    assert rows["银行"]["mom_20d"] > rows["半导体"]["mom_20d"]
    assert rows["银行"]["flow_20d"] > rows["半导体"]["flow_20d"]
    assert rows["银行"]["pe_med"] < rows["半导体"]["pe_med"]
    assert rows["银行"]["total_score"] > rows["半导体"]["total_score"]


def test_rotation_skips_small_industries():
    basic, daily, flow, dbasic = _fixtures()
    # 加入一个 2 只票的小行业，应被 min_members 过滤
    extra = pd.DataFrame({"ts_code": ["300001.SZ", "300002.SZ"],
                          "industry": ["贵金属", "贵金属"]})
    basic = pd.concat([basic, extra], ignore_index=True)
    rows = []
    for code in extra["ts_code"]:
        price = 10.0
        for d in sorted(daily["trade_date"].unique()):
            price *= 1.001
            rows.append({"ts_code": code, "trade_date": d, "open": price,
                         "close": price, "vol": 100.0})
    daily = pd.concat([daily, pd.DataFrame(rows)], ignore_index=True)
    flow_extra = pd.DataFrame([
        {"ts_code": c, "trade_date": d, "buy_lg_amount": 10, "buy_elg_amount": 10,
         "sell_lg_amount": 0, "sell_elg_amount": 0}
        for c in extra["ts_code"] for d in sorted(daily["trade_date"].unique())
    ])
    flow = pd.concat([flow, flow_extra], ignore_index=True)
    db_extra = pd.DataFrame([
        {"ts_code": c, "trade_date": d, "pe_ttm": 30.0}
        for c in extra["ts_code"] for d in sorted(daily["trade_date"].unique())
    ])
    dbasic = pd.concat([dbasic, db_extra], ignore_index=True)

    reader = _FakeReader(basic, daily, flow, dbasic)
    result = IndustryRotationService(reader).run(months=12, force_refresh=True)
    assert "error" not in result
    names = {r["industry"] for r in result["rows"]}
    assert "贵金属" not in names
    assert "银行" in names and "半导体" in names


def test_rotation_without_moneyflow():
    basic, daily, _, dbasic = _fixtures()
    reader = _FakeReader(basic, daily, pd.DataFrame(), dbasic)
    result = IndustryRotationService(reader).run(months=12, force_refresh=True)
    assert "error" not in result
    assert result["meta"]["has_moneyflow"] is False
    for row in result["rows"]:
        assert row["flow_5d"] is None and row["flow_z"] is None
