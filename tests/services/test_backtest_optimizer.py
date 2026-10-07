"""回测参数寻优测试：网格展开、网格搜索、walk-forward 滚动样本外。"""

from __future__ import annotations

import math

import pytest

from app.services.backtest_optimizer import BacktestOptimizerService, expand_grid


N_DAYS = 300


def _dates():
    import pandas as pd
    return pd.bdate_range("2026-01-01", periods=N_DAYS).strftime("%Y-%m-%d").tolist()


def _history():
    # 震荡序列（sin 波），均线/RSI/KDJ 策略都能产生信号
    dates = _dates()
    rows = []
    for i, d in enumerate(dates):
        price = 10 * (1 + 0.15 * math.sin(i / 12))
        rows.append({
            "ts_code": "T.DEBUT", "trade_date": d,
            "open": price * 0.999, "close": price,
            "high": price * 1.01, "low": price * 0.99,
            "vol": 10000.0, "amount": price * 10000.0,
        })
    return rows


def _factors():
    dates = _dates()
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "trade_date": d,
            "rsi_6": 50 + 45 * math.sin(i / 7),       # 周期性穿越 30/70
            "kdj_k": 50 + 45 * math.sin(i / 6),
            "macd": math.sin(i / 9), "macd_dea": math.sin((i - 1) / 9),
            "boll_upper": 12.0, "boll_lower": 8.0,
        })
    return rows


@pytest.fixture()
def patched_stock_service(monkeypatch):
    import app.services.backtest_optimizer as opt_mod

    class _FakeStockService:
        @staticmethod
        def get_daily_history(ts_code, start_date=None, end_date=None, limit=60):
            return [r for r in _history() if (start_date or "") <= r["trade_date"] <= (end_date or "9999")]

        @staticmethod
        def get_stock_factors(ts_code, start_date=None, end_date=None, limit=60):
            return [r for r in _factors() if (start_date or "") <= r["trade_date"] <= (end_date or "9999")]

    monkeypatch.setattr(opt_mod, "StockService", _FakeStockService)


class TestExpandGrid:
    def test_ma_cross_filters_invalid(self):
        combos = expand_grid("ma_cross")
        assert all(c["ma_short"] < c["ma_long"] for c in combos)
        assert len(combos) > 0

    def test_kdj_rsi_filters_invalid(self):
        for st in ("kdj", "rsi"):
            combos = expand_grid(st)
            assert all(c["oversold"] < c["overbought"] for c in combos)

    def test_custom_grid(self):
        combos = expand_grid("rsi", {"oversold": [25], "overbought": [70, 75]})
        assert combos == [{"oversold": 25, "overbought": 70}, {"oversold": 25, "overbought": 75}]

    def test_unknown_strategy_empty(self):
        assert expand_grid("nope") == []


class TestGridSearch:
    def test_ranks_and_best(self, patched_stock_service):
        svc = BacktestOptimizerService()
        result = svc.grid_search("T.DEBUT", "rsi", "2026-02-01", "2026-09-30")
        assert "error" not in result
        assert result["n_combos"] == 9
        assert result["best"] is not None
        metrics = [r.get("sharpe_ratio") for r in result["results"] if r["valid"]]
        ranked = [r.get("sharpe_ratio") for r in result["results"] if r["valid"]]
        assert ranked == sorted(metrics, reverse=True)

    def test_unsupported_strategy(self, patched_stock_service):
        svc = BacktestOptimizerService()
        result = svc.grid_search("T.DEBUT", "bollinger", "2026-02-01", "2026-09-30")
        assert "error" in result

    def test_custom_grid_respected(self, patched_stock_service):
        svc = BacktestOptimizerService()
        result = svc.grid_search("T.DEBUT", "rsi", "2026-02-01", "2026-09-30",
                                 grid={"oversold": [20], "overbought": [80]})
        assert result["n_combos"] == 1
        assert result["best"]["params"] == {"oversold": 20, "overbought": 80}


class TestWalkForward:
    def test_windows_and_stability(self, patched_stock_service):
        svc = BacktestOptimizerService()
        result = svc.walk_forward("T.DEBUT", "rsi", "2026-01-01", "2026-12-31",
                                  is_days=60, oos_days=40)
        assert "error" not in result
        assert result["summary"]["n_windows"] >= 3
        # OOS 不重叠：后一窗的 oos_start > 前一窗的 oos_end
        wins = result["windows"]
        for a, b in zip(wins, wins[1:]):
            assert b["oos_start"] > a["oos_end"]
        # 参数稳定性已记录
        assert result["param_stability"]["oversold"]
        s = result["summary"]
        assert s["oos_hit_rate"] is not None or s["n_oos_valid"] == 0
        assert "note" in result

    def test_insufficient_dates(self, patched_stock_service):
        svc = BacktestOptimizerService()
        result = svc.walk_forward("T.DEBUT", "rsi", "2026-01-01", "2026-02-28",
                                  is_days=120, oos_days=60)
        assert "error" in result
