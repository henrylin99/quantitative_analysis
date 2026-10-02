"""Alpha191 因子服务测试 — 合成数据验证公式与输出 schema。"""
import numpy as np
import pandas as pd
import pytest

from app.services.alpha191_factor_service import (
    ALPHA191_FACTORS,
    SKIP_FACTORS,
    Alpha191Calculator,
    Alpha191FactorService,
    Alpha191Panel,
)


def _make_panel(n_days: int = 10, n_stocks: int = 5, seed: int = 42) -> Alpha191Panel:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-01-05", periods=n_days)
    cols = [f"00000{i}.SZ" for i in range(n_stocks)]

    def wide(base, scale):
        return pd.DataFrame(
            base + rng.normal(0, scale, size=(n_days, n_stocks)).cumsum(axis=0),
            index=dates, columns=cols,
        )

    close = wide(10.0, 0.2)
    open_ = (close * (1 + rng.normal(0, 0.01, size=(n_days, n_stocks)))).clip(lower=1)
    high = close * 1.02
    low = close * 0.98
    pre_close = close.shift(1).fillna(close.iloc[0])
    volume = pd.DataFrame(
        rng.integers(1000, 5000, size=(n_days, n_stocks)).astype(float),
        index=dates, columns=cols,
    )
    return Alpha191Panel(
        open=open_, high=high, low=low, close=close, pre_close=pre_close,
        volume=volume, amount=volume * 1000, vwap=close,
    )


class TestAlpha001:
    def test_matches_independent_reference_computation(self):
        """与独立推导对照：截面 pct-rank 后 6 日滚动 Pearson 相关取负。"""
        from scipy.stats import pearsonr

        panel = _make_panel(n_days=12)
        raw = Alpha191Calculator().alpha_001(panel)
        # ±inf 是 pandas 滚动相关的零方差边界产出，统一按缺失处理
        # （与参考实现的源头清洗、服务层落库边界同口径）
        result = raw.replace([np.inf, -np.inf], np.nan)

        log_vol = np.log(panel.volume.where(panel.volume > 0))
        r1 = log_vol.diff(1).rank(axis=1, pct=True)
        r2 = ((panel.close - panel.open) / panel.open).rank(axis=1, pct=True)

        for stock in panel.close.columns:
            for t in range(len(panel.close)):
                window1 = r1[stock].iloc[max(0, t - 5): t + 1]
                window2 = r2[stock].iloc[max(0, t - 5): t + 1]
                valid = window1.notna() & window2.notna()
                if valid.sum() < 2:
                    expected = np.nan
                else:
                    expected = -pearsonr(window1[valid], window2[valid])[0]
                actual = result[stock].iloc[t]
                if np.isnan(expected):
                    assert np.isnan(actual)
                else:
                    assert actual == pytest.approx(expected, abs=1e-10)

    def test_alpha_002_matches_delta_formula(self):
        """平移正确性抽验：alpha_002 = -DELTA(价格位置, 1)。"""
        panel = _make_panel()
        result = Alpha191Calculator().alpha_002(panel).replace(
            [np.inf, -np.inf], np.nan
        )
        price_pos = ((panel.close - panel.low) - (panel.high - panel.close)) / (
            panel.high - panel.low
        )
        expected = -price_pos.diff(1)
        pd.testing.assert_frame_equal(result, expected)

    def test_zero_volume_becomes_nan(self):
        panel = _make_panel()
        panel.volume.iloc[0, 0] = 0
        result = Alpha191Calculator().alpha_001(panel)
        # log(0) 无定义 → 早期滚动窗无效，该股票早期值应为 NaN 而非报错
        assert np.isnan(result.iloc[0, 0])

    def test_inf_filtered_in_calculate_output(self):
        """服务层输出不得含 ±inf。"""
        service = Alpha191FactorService()
        panel = _make_panel()
        wide = Alpha191Calculator().alpha_001(panel).replace(0.0, np.inf)
        long_df = service._to_long(wide, "alpha_001")
        assert not np.isinf(long_df["factor_value"]).any()
        assert list(long_df.columns) == ["ts_code", "trade_date", "factor_id", "factor_value"]


class TestFactorRegistry:
    def test_all_191_factors_registered(self):
        methods = {
            n for n in dir(Alpha191Calculator) if n.startswith("alpha_")
        }
        assert set(ALPHA191_FACTORS) == methods
        assert len(methods) == 191

    def test_skip_factors_marked(self):
        assert set(SKIP_FACTORS) == {"alpha_030", "alpha_143"}
        assert "skip_reason" in ALPHA191_FACTORS["alpha_030"]

    def test_alpha_001_metadata(self):
        meta = ALPHA191_FACTORS["alpha_001"]
        assert meta["formula"].startswith("-CORR")
        assert meta["warmup_days"] >= 12

    def test_list_factors_contains_metadata(self):
        factors = Alpha191FactorService.list_factors()
        ids = {f["factor_id"] for f in factors}
        assert {"alpha_001", "alpha_002", "alpha_191"} <= ids
