"""信号定义共享模块测试：阈值解析、掩码 Series/DataFrame 一致性、回测阈值覆盖。"""

from __future__ import annotations

import pandas as pd

from app.services.signal_defs import (
    DEFAULT_THRESHOLDS,
    SIGNAL_LABELS,
    SignalThresholds,
    divergence_mask,
    resonance_mask,
    signal_definitions,
    squeeze_mask,
)


class TestSignalThresholds:
    def test_from_params_overrides_valid_keys(self):
        t = SignalThresholds.from_params({
            "squeeze_winner_min": "55",
            "resonance_winner_hi": "75",
        })
        assert t.squeeze_winner_min == 55.0
        assert t.resonance_winner_hi == 75.0
        # 未覆盖字段保持默认
        assert t.divergence_winner_min == DEFAULT_THRESHOLDS.divergence_winner_min

    def test_from_params_ignores_invalid(self):
        t = SignalThresholds.from_params({
            "bogus_key": "3",                # 未知键忽略
            "divergence_pct5d_min": "abc",   # 非法值回退
            "squeeze_conc_quantile": "",     # 空串回退
            "resonance_winner_lo": None,     # None 回退
        })
        assert t == DEFAULT_THRESHOLDS

    def test_from_params_none_returns_default(self):
        assert SignalThresholds.from_params(None) == DEFAULT_THRESHOLDS

    def test_signature_distinguishes_instances(self):
        t = SignalThresholds.from_params({"squeeze_winner_min": "55"})
        assert t.signature() != DEFAULT_THRESHOLDS.signature()
        assert DEFAULT_THRESHOLDS.signature() == SignalThresholds().signature()


class TestMasks:
    def _series(self):
        # (winner, conc, vol_ratio, pct5) 三票：命中 / 获利盘不足 / 集中度松
        return (
            pd.Series([65.0, 50.0, 70.0]),
            pd.Series([0.05, 0.05, 0.50]),
            pd.Series([0.80, 0.80, 0.90]),
            pd.Series([0.05, 0.05, 0.20]),
        )

    def test_squeeze_series(self):
        w, c, v, p = self._series()
        mask = squeeze_mask(w, c, 0.20, v, p)
        assert list(mask) == [True, False, False]

    def test_squeeze_dataframe_with_row_thresholds(self):
        w, c, v, p = self._series()
        df = lambda s: s.to_frame("a")
        mask = squeeze_mask(df(w), df(c), pd.Series([0.20] * 3), df(v), df(p))
        assert list(mask["a"]) == [True, False, False]

    def test_resonance_and_divergence(self):
        w = pd.Series([65.0, 50.0, 70.0])
        net5 = pd.Series([100.0, -5.0, 100.0])
        net_last = pd.Series([50.0, -1.0, 50.0])
        chg = pd.Series([5.0, 5.0, 5.0])
        pct5 = pd.Series([0.05, 0.05, 0.20])
        res = resonance_mask(net5, net_last, chg, w, pct5)
        assert list(res) == [True, False, True]  # 70 含于 [30, 70]
        div = divergence_mask(pd.Series([0.05]), pd.Series([-100.0]), pd.Series([75.0]))
        assert bool(div.iloc[0]) is True

    def test_definitions_text_uses_overridden_values(self):
        t = SignalThresholds.from_params({
            "squeeze_winner_min": "55",
            "squeeze_conc_quantile": "0.1",
        })
        defs = signal_definitions(t, conc_thresh=0.18)
        assert "55" in defs["squeeze"]
        assert "10%分位" in defs["squeeze"]
        assert "0.18" in defs["squeeze"]
        base = signal_definitions(DEFAULT_THRESHOLDS)
        assert set(base) == {"squeeze", "resonance", "divergence"}


class TestBacktestThresholdOverride:
    def test_backtest_accepts_thresholds_and_echoes(self, monkeypatch):
        from app.services.signal_backtest_service import ChipSignalBacktestService

        dates = pd.bdate_range("2026-06-01", periods=60).strftime("%Y-%m-%d").tolist()
        codes = ["A.DEBUT", "B.DEBUT"]
        cyq = pd.DataFrame([
            {"ts_code": c, "trade_date": d, "winner_rate": 65.0,
             "cost_95pct": 11.0, "cost_5pct": 9.0, "cost_50pct": 10.0}
            for c in codes for d in dates
        ])
        # 量能几何衰减 → 后段 5日均量/20日均量 < 0.85，squeeze 满足量能收缩条件
        vols = [2000.0 * (0.96 ** i) for i in range(len(dates))]
        daily = pd.DataFrame([
            {"ts_code": c, "trade_date": d, "open": 10.0, "close": 10.0, "vol": vol}
            for c in codes for d, vol in zip(dates, vols)
        ])
        flow = pd.DataFrame([
            {"ts_code": c, "trade_date": d, "buy_lg_amount": 500.0,
             "buy_elg_amount": 500.0, "sell_lg_amount": 0.0, "sell_elg_amount": 0.0}
            for c in codes for d in dates
        ])
        svc = ChipSignalBacktestService(_FakeReader(cyq, daily, flow))

        custom = SignalThresholds.from_params({"squeeze_winner_min": "80"})
        r1 = svc.run(months=6, force_refresh=True, thresholds=custom)
        assert "error" not in r1
        assert r1["thresholds"]["squeeze_winner_min"] == 80.0
        # 自定义阈值下获利盘 65 不再触发 squeeze
        assert r1["signals"]["squeeze"]["horizons"]["h20"]["n_events"] == 0

        r2 = svc.run(months=6, force_refresh=False)  # 默认阈值 → 缓存键不同 → 重算
        assert "error" not in r2
        assert r2["thresholds"]["squeeze_winner_min"] == 60.0
        assert r2["signals"]["squeeze"]["horizons"]["h20"]["n_events"] > 0


class _FakeReader:
    def __init__(self, cyq, daily, flow):
        self._cyq, self._daily, self._flow = cyq, daily, flow

    def get_cyq_perf(self, ts_codes=None, start_date=None, end_date=None):
        return self._cyq.copy()

    def get_daily(self, ts_codes=None, start_date=None, end_date=None):
        return self._daily.copy()

    def get_moneyflow(self, ts_codes=None, start_date=None, end_date=None):
        return self._flow.copy()
