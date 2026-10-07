"""信号回测服务测试：合成数据验证前向收益口径（T+1 开 → T+1+H 开）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.signal_backtest_service import (
    AnomalyForwardService,
    ChipSignalBacktestService,
)


class _FakeReader:
    """按表名返回预置 DataFrame 的读桩。"""

    def __init__(self, cyq=None, daily=None, flow=None, income=None, balance=None, cash=None):
        self._tables = {
            "cyq": cyq if cyq is not None else pd.DataFrame(),
            "daily": daily if daily is not None else pd.DataFrame(),
            "flow": flow if flow is not None else pd.DataFrame(),
            "income": income if income is not None else pd.DataFrame(),
            "balance": balance if balance is not None else pd.DataFrame(),
            "cash": cash if cash is not None else pd.DataFrame(),
        }

    def get_cyq_perf(self, ts_codes=None, start_date=None, end_date=None):
        return self._tables["cyq"].copy()

    def get_daily(self, ts_codes=None, start_date=None, end_date=None):
        df = self._tables["daily"].copy()
        if ts_codes is not None:
            df = df[df["ts_code"].isin(set(ts_codes))]
        return df

    def get_moneyflow(self, ts_codes=None, start_date=None, end_date=None):
        return self._tables["flow"].copy()

    def get_income_statement(self, ts_codes):
        return self._tables["income"].copy()

    def get_balance_sheet(self, ts_codes):
        return self._tables["balance"].copy()

    def get_cash_flow(self, ts_codes):
        return self._tables["cash"].copy()


def _make_daily(codes, dates, base=10.0, drift=0.001):
    rows = []
    for c in codes:
        price = base
        for d in dates:
            price *= 1 + drift
            rows.append({"ts_code": c, "trade_date": d, "open": price,
                         "close": price, "vol": 1000.0})
    return pd.DataFrame(rows)


def _make_cyq(codes, dates, winner=65.0):
    rows = []
    for c in codes:
        for d in dates:
            rows.append({"ts_code": c, "trade_date": d, "winner_rate": winner,
                         "cost_95pct": 11.0, "cost_5pct": 9.0, "cost_50pct": 10.0})
    return pd.DataFrame(rows)


def _make_flow(codes, dates, net=500.0):
    rows = []
    for c in codes:
        for d in dates:
            rows.append({"ts_code": c, "trade_date": d,
                         "buy_lg_amount": net, "buy_elg_amount": net,
                         "sell_lg_amount": 0.0, "sell_elg_amount": 0.0})
    return pd.DataFrame(rows)


def _trading_dates(n=60, start="2026-06-01"):
    return pd.bdate_range(start, periods=n).strftime("%Y-%m-%d").tolist()


class TestChipSignalBacktest:
    def test_empty_data_returns_error(self):
        svc = ChipSignalBacktestService(_FakeReader())
        result = svc.run(months=12, force_refresh=True)
        assert "error" in result

    def test_squeeze_triggers_and_stats_present(self):
        codes = [f"00000{i}.SZ" for i in range(6)]
        dates = _trading_dates(60)
        reader = _FakeReader(
            cyq=_make_cyq(codes, dates, winner=65.0),
            daily=_make_daily(codes, dates),
            flow=_make_flow(codes, dates),
        )
        svc = ChipSignalBacktestService(reader)
        result = svc.run(months=12, force_refresh=True)

        assert "error" not in result
        assert result["meta"]["n_days"] > 0
        for name in ("squeeze", "resonance", "divergence"):
            assert name in result["signals"]
            for h in ("h5", "h10", "h20"):
                stats = result["signals"][name]["horizons"][h]
                assert "n_days" in stats and "excess_t" in stats
        # 所有股票 winner=65、conc=0.2、量能比=1 → squeeze 不触发（量能比>0.85）
        assert result["signals"]["squeeze"]["horizons"]["h5"]["n_days"] == 0

    def test_resonance_triggers_with_positive_flow(self):
        codes = [f"00000{i}.SZ" for i in range(6)]
        dates = _trading_dates(60)
        # 价格单边上行 → pct5>0；winner=50 处于 30~70；winner 恒定 → chg=0
        # 因此构造 winner 逐日抬升：用两段 winner
        cyq = _make_cyq(codes, dates, winner=40.0)
        cyq.loc[cyq["trade_date"] >= dates[30], "winner_rate"] = 55.0
        reader = _FakeReader(
            cyq=cyq, daily=_make_daily(codes, dates, drift=0.005),
            flow=_make_flow(codes, dates),
        )
        result = ChipSignalBacktestService(reader).run(months=12, force_refresh=True)
        res = result["signals"]["resonance"]["horizons"]["h5"]
        assert res["n_days"] > 0
        assert res["n_events"] > 0
        # 单边上行 + 正资金流 → 日均收益应为正
        assert res["mean_ret_bp"] > 0

    def test_forward_return_matches_manual_calc(self):
        """多票同日触发：验证 T+1 开 → T+1+H 开 的收益进入日均。"""
        codes = [f"00000{i}.SZ" for i in range(6)]
        dates = _trading_dates(40)
        opens = np.linspace(10.0, 14.0, len(dates))
        rows = []
        for c in codes:
            for d, o in zip(dates, opens):
                rows.append({"ts_code": c, "trade_date": d,
                             "open": o, "close": o + 0.1, "vol": 1000.0})
        daily = pd.DataFrame(rows)
        cyq = _make_cyq(codes, dates, winner=40.0)
        # dates[20] 起获利盘抬升到 55（仍 <70），diff(5) 在 dates[20..24] > 0
        cyq.loc[cyq["trade_date"] >= dates[20], "winner_rate"] = 55.0
        reader = _FakeReader(cyq=cyq, daily=daily, flow=_make_flow(codes, dates))
        result = ChipSignalBacktestService(reader).run(months=12, force_refresh=True)

        res = result["signals"]["resonance"]["horizons"]["h5"]
        assert res["n_days"] == 5  # diff(5)>0 的日子：dates[20..24]
        # 逐日期望：入场 open[t+1]，5 日后出场 open[t+6]，对 6 票等权（同价）＝单票值
        per_day = [opens[t + 6] / opens[t + 1] - 1 for t in range(20, 25)]
        # 服务端 mean_ret_bp 保留 2 位小数
        assert res["mean_ret_bp"] == pytest.approx(float(np.mean(per_day)) * 1e4, abs=0.01)


class TestAnomalyForward:
    def _fin_tables(self):
        inc_rows, bal_rows, cash_rows = [], [], []
        for i in range(4):
            code = f"00000{i}.SZ"
            for year in ("2024", "2025"):
                end = f"{year}1231"
                rev = 1000.0
                profit = 50.0
                f_ann = f"{int(year) + 1}-03-16"  # 周一，避免周末不在交易日序列
                inc_rows.append({"ts_code": code, "end_date": end, "report_type": "1",
                                 "revenue": rev, "n_income_attr_p": profit,
                                 "oper_cost": 600.0, "f_ann_date": f_ann, "ann_date": f_ann})
                # 2025 应收暴增（000000.SZ 除外，留作对照组）
                if year == "2024":
                    rec = 100.0
                else:
                    rec = 110.0 if code == "000000.SZ" else 500.0
                bal_rows.append({"ts_code": code, "end_date": end,
                                 "accounts_receiv": rec, "inventories": 100.0})
                cash_rows.append({"ts_code": code, "end_date": end,
                                  "n_cashflow_act": 200.0})
        return (pd.DataFrame(inc_rows), pd.DataFrame(bal_rows), pd.DataFrame(cash_rows))

    def test_anomaly_forward_groups(self, monkeypatch):
        income, balance, cash = self._fin_tables()
        codes = income["ts_code"].unique().tolist()
        dates = _trading_dates(150, start="2026-02-01")  # 覆盖披露日 2026-03-15 前后
        reader = _FakeReader(income=income, balance=balance, cash=cash,
                             daily=_make_daily(codes, dates))
        # _read_recent_years 是目录扫描方法，打桩为直接返回预置表
        from app.services import financial_quality_service as fq_mod

        tables = {"income_statement": income, "balance_sheet": balance, "cash_flow": cash}
        monkeypatch.setattr(
            fq_mod.FinancialQualityService, "_read_recent_years",
            lambda self, table: tables[table].copy(),
        )
        svc = AnomalyForwardService(reader)
        result = svc.run(force_refresh=True)

        assert "error" not in result
        assert result["report_year"] == "2025"
        assert "receiv_gap" in result["groups"]
        assert "clean" in result["groups"]
        # 应收增速 400% vs 营收 0% → receiv_gap 命中（对照组除外）
        assert result["groups"]["receiv_gap"]["n_stocks"] == len(codes) - 1
        h5 = result["groups"]["clean"]["h5"]
        assert h5["n"] > 0
        assert h5["mean_ret_bp"] is not None
