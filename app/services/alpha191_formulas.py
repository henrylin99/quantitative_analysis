"""
Alpha191 公式库 — 从 20260213 项目 backend/app/factors/alpha191_new.py 整体平移
（2026-10-02 整合，公式与算子保持逐行一致，零转写改动）。

包含：Alpha191Panel 宽面板定义、Alpha191Calculator 全部 191 个 alpha_NNN
因子方法与向量化算子（rank/corr/ts_rank/decay_linear/sma/wma 等）。
数据加载与落库编排见 alpha191_factor_service.Alpha191FactorService。

已知不可计算的因子（调用会抛 NotImplementedError）：
    alpha_030 — 需要 Fama-French 三因子数据（MKT/SMB/HML）
    alpha_143 — 旧公式含递归 SELF 状态
基准指数依赖因子（benchmark_open/close 为 None 时结果为空/NaN）：
    alpha_075 / alpha_149 / alpha_181 / alpha_182
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


@dataclass
class Alpha191Panel:
    """日期(行) × 股票(列) 的宽面板。"""
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    pre_close: pd.DataFrame
    volume: pd.DataFrame
    amount: pd.DataFrame
    vwap: pd.DataFrame
    turnover_rate: Optional[pd.DataFrame] = None
    volume_ratio: Optional[pd.DataFrame] = None
    total_mv: Optional[pd.DataFrame] = None
    circ_mv: Optional[pd.DataFrame] = None
    benchmark_open: Optional[pd.DataFrame] = None
    benchmark_close: Optional[pd.DataFrame] = None

def _safe_div(numerator: pd.DataFrame, denominator: pd.DataFrame) -> pd.DataFrame:
    """Element-wise division with zero/NaN protection: denominator==0 → NaN,
    结果中的 ±inf 一律置 NaN,避免 inf 污染后续 rolling/rank 计算。"""
    denom = denominator.where(denominator != 0, np.nan)
    out = numerator / denom
    return out.replace([np.inf, -np.inf], np.nan)


def _nan_safe_arg_reduce(windows: np.ndarray, kind: str) -> np.ndarray:
    """argmin/argmax on the last axis;窗口含 NaN(停牌缺行)时返回 -1,由调用方置 NaN。

    否则 np.argmin/argmax 会把 NaN 位置当极值返回,产生垃圾索引。
    """
    fn = np.argmin if kind == "min" else np.argmax
    pos = fn(windows, axis=-1)
    nan_mask = np.isnan(windows).any(axis=-1)
    return np.where(nan_mask, -1, pos)
class Alpha191Calculator:
    """Reusable Alpha191 operators and factor calculation entrypoints."""

    def __init__(self, loader=None) -> None:
        self.loader = loader  # 数据加载由 Alpha191FactorService 负责

    @staticmethod
    def decay_linear_series(values: pd.Series) -> float:
        weights = pd.Series(range(1, len(values) + 1), index=values.index, dtype=float)
        return float((values * weights).sum() / weights.sum())

    def delay(self, data: pd.DataFrame, periods: int) -> pd.DataFrame:
        return data.shift(periods)

    def delta(self, data: pd.DataFrame, periods: int) -> pd.DataFrame:
        return data.diff(periods)

    def ts_sum(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        return data.rolling(window).sum()

    def ts_mean(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        return data.rolling(window).mean()

    def ts_stddev(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        return data.rolling(window).std()

    def ts_min(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        return data.rolling(window).min()

    def ts_max(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        return data.rolling(window).max()

    def ewma(self, data: pd.DataFrame, alpha: float) -> pd.DataFrame:
        return data.ewm(alpha=alpha, adjust=False).mean()

    def rank(self, data: pd.DataFrame) -> pd.DataFrame:
        return data.rank(axis=1, pct=True)

    def ts_rank(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        """Vectorized ts_rank using sliding_window_view for significant speedup.

        The ts_rank formula is: rank(values, pct=True)[-1]
        i.e., the percentile rank of the last value in each rolling window.

        Matches the old rolling.apply semantics exactly:
        - Windows containing any non-finite value (NaN or inf/-inf) → NaN
        - Ties use average ranking (pandas rank default)

        Old implementation: rolling.apply with Python function (slow)
        New implementation: numpy vectorized (fast)
        """
        values = data.to_numpy(dtype=float)
        n_rows, n_cols = values.shape
        result = np.full_like(values, np.nan)

        if n_rows < window:
            return pd.DataFrame(result, index=data.index, columns=data.columns)

        # Create sliding windows
        # Shape: (n_rows - window + 1, n_cols, window)
        windows = sliding_window_view(values, window, axis=0)
        n_windows = windows.shape[0]

        # Non-finite mask: windows with any NaN or inf/-inf → NaN
        has_nonfinite = ~np.isfinite(windows).all(axis=2)  # (n_windows, n_cols)

        # Last values in each window
        last_values = windows[:, :, -1]  # (n_windows, n_cols)
        last_is_nonfinite = ~np.isfinite(last_values)

        # For valid windows, compute average-rank of the last value.
        # Average rank of value v in array a = (count(<v) + count(<=v) + 1) / 2
        # pct = average_rank / window
        lt_count = (windows < last_values[:, :, np.newaxis]).sum(
            axis=2
        )  # count strictly less
        le_count = (windows <= last_values[:, :, np.newaxis]).sum(
            axis=2
        )  # count less-or-equal
        # (lt + le + 1) / 2 = average rank (1-based); / window = pct
        ranks = (lt_count.astype(float) + le_count.astype(float) + 1.0) / (2.0 * window)

        # Apply non-finite masks
        ranks[has_nonfinite | last_is_nonfinite] = np.nan

        result[window - 1 :, :] = ranks
        return pd.DataFrame(result, index=data.index, columns=data.columns)

    def corr(
        self, left: pd.DataFrame, right: pd.DataFrame, window: int
    ) -> pd.DataFrame:
        return left.rolling(window).corr(right)

    def decay_linear(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        """Vectorized decay_linear using sliding_window_view for 10-100x speedup.

        The decay_linear formula is: sum(values * weights) / sum(weights)
        where weights = [1, 2, 3, ..., window] (linearly increasing).

        Matches old rolling.apply semantics:
        - Window containing any NaN → NaN
        - Window containing any inf/-inf → NaN

        Old implementation: rolling.apply with Python function (10+ seconds)
        New implementation: numpy vectorized (0.1-0.5 seconds)
        """
        values = data.to_numpy(dtype=float)
        n_rows, n_cols = values.shape

        if n_rows < window:
            # Not enough data, return NaN
            result = np.full_like(values, np.nan)
        else:
            # Create sliding windows
            windows = sliding_window_view(values, window, axis=0)

            # Create weights [1, 2, ..., window]
            weights = np.arange(1, window + 1, dtype=float)

            # Compute weighted sum: sum(window * weights) / sum(weights)
            # windows shape: (n_rows - window + 1, n_cols, window)
            weighted_sum = np.dot(
                windows, weights
            )  # shape: (n_rows - window + 1, n_cols)
            weight_sum = weights.sum()

            # NaN mask: windows with any non-finite value (NaN or inf/-inf) → NaN
            has_nonfinite = ~np.isfinite(windows).all(axis=2)  # (n_windows, n_cols)

            # Fill result with NaNs for the first (window-1) rows
            result = np.full_like(values, np.nan)
            result[window - 1 :] = weighted_sum / weight_sum

            # Apply non-finite mask
            result[window - 1 :][has_nonfinite] = np.nan

        return pd.DataFrame(result, index=data.index, columns=data.columns)

    def sma(self, data: pd.DataFrame, window: int, m: int = 1) -> pd.DataFrame:
        alpha = m / float(window)
        return data.ewm(alpha=alpha, adjust=False).mean()

    def wma(self, data: pd.DataFrame, window: int) -> pd.DataFrame:
        """
        Vectorized WMA with 0.9^(n-i-1) decay weights (newest observation weighs 1.0).

        Matches rolling(window).apply semantics exactly: windows containing any
        NaN yield NaN (min_periods defaults to the window size), and rows
        without a full window are NaN.
        """
        # weights[j] is the weight of the element lagged (window-1-j) rows.
        weights = 0.9 ** np.arange(window - 1, -1, -1)
        numerator = None
        invalid = None
        for j, w in enumerate(weights):
            lagged = data.shift(window - 1 - j)
            notna = lagged.notna()
            invalid = ~notna if invalid is None else invalid | ~notna
            contribution = lagged.fillna(0.0) * w
            numerator = contribution if numerator is None else numerator + contribution
        result = numerator / weights.sum()
        return result.where(~invalid)

    @staticmethod
    def _weighted_rolling_sum(data: pd.DataFrame, weights: np.ndarray) -> pd.DataFrame:
        """Σ_j weights[j] · x.shift(len(weights)-1-j), i.e. the rolling dot
        product Σ(weights, window) without a per-window Python call.

        NaN propagates through the additions, matching
        rolling(window).apply(lambda v: float(np.dot(weights, v)), raw=True).
        """
        out = None
        for j, w in enumerate(weights):
            lagged = data.shift(len(weights) - 1 - j)
            out = lagged * w if out is None else out + lagged * w
        return out

    def alpha_001(self, panel: Alpha191Panel) -> pd.DataFrame:
        log_volume = panel.volume.where(panel.volume > 0)
        data1 = self.rank(self.delta(np.log(log_volume), 1))
        data2 = self.rank((panel.close - panel.open) / panel.open)
        # min_periods=2 mirrors the old iloc[-6:].corrwith(...) behavior, which
        # dropped pairwise-NaN rows and accepted as few as 2 valid pairs.
        return -data1.rolling(6, min_periods=2).corr(data2)

    def alpha_002(self, panel: Alpha191Panel) -> pd.DataFrame:
        price_position = ((panel.close - panel.low) - (panel.high - panel.close)) / (
            panel.high - panel.low
        )
        return -self.delta(price_position, 1)

    def alpha_003(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_close = self.delay(panel.close, 1)
        equal = panel.close == delay_close
        greater = panel.close > delay_close
        lower = panel.close < delay_close

        up_base = delay_close.where(delay_close <= panel.low, panel.low)
        down_base = delay_close.where(delay_close >= panel.high, panel.high)

        part_up = (panel.close - up_base).where(greater, 0.0)
        part_down = (panel.close - down_base).where(lower, 0.0)
        per_day = part_up.where(~equal, 0.0) + part_down.where(~equal, 0.0)
        return per_day.rolling(6).sum()

    def alpha_004(self, panel: Alpha191Panel) -> pd.DataFrame:
        close_std_8 = self.ts_stddev(panel.close, 8)
        close_mean_2 = self.ts_sum(panel.close, 2) / 2.0
        close_mean_8 = self.ts_sum(panel.close, 8) / 8.0
        volume_ratio = panel.volume / self.ts_mean(panel.volume, 20)

        condition1 = (close_mean_8 + close_std_8) < close_mean_2
        condition2 = close_mean_2 < (close_mean_8 - close_std_8)
        condition3 = volume_ratio >= 1.0

        result = pd.DataFrame(
            -1.0, index=panel.close.index, columns=panel.close.columns
        )
        result = result.mask(~condition1 & condition2, 1.0)
        result = result.mask(~condition1 & ~condition2 & condition3, 1.0)
        result = result.mask(~condition1 & ~condition2 & ~condition3, -1.0)
        return result

    def alpha_005(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized over all dates. Uses pandas rolling.rank (>=1.4) to avoid
        # the per-window Python callback path that made the old ts_rank slow.
        ts_volume_rank = panel.volume.rolling(5).rank(pct=True)
        ts_high_rank = panel.high.rolling(5).rank(pct=True)
        corr_ts = ts_high_rank.rolling(5).corr(ts_volume_rank)
        return -corr_ts.rolling(3).max()

    def alpha_006(self, panel: Alpha191Panel) -> pd.DataFrame:
        signal = self.delta(panel.open * 0.85 + panel.high * 0.15, 4)
        return -self.rank(np.sign(signal))

    def alpha_007(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta_vwap_close = panel.vwap - panel.close
        part1 = self.rank(np.maximum(delta_vwap_close, 3))
        part2 = self.rank(np.minimum(delta_vwap_close, 3))
        part3 = self.rank(self.delta(panel.volume, 3))
        return (part1 + part2) * part3

    def alpha_008(self, panel: Alpha191Panel) -> pd.DataFrame:
        temp = ((panel.high + panel.low) * 0.2 / 2.0) + panel.vwap * 0.8
        return self.rank(-self.delta(temp, 4))

    def alpha_009(self, panel: Alpha191Panel) -> pd.DataFrame:
        temp = (
            (
                ((panel.high + panel.low) * 0.5)
                - ((self.delay(panel.high, 1) + self.delay(panel.low, 1)) * 0.5)
            )
            * (panel.high - panel.low)
            / panel.volume
        )
        return self.ewma(temp, alpha=2 / 7)

    def alpha_010(self, panel: Alpha191Panel) -> pd.DataFrame:
        returns = panel.close / self.delay(panel.close, 1) - 1.0
        base = self.ts_stddev(returns, 20).where(returns < 0, panel.close)
        return self.rank(self.ts_max(base**2, 5))

    def alpha_011(self, panel: Alpha191Panel) -> pd.DataFrame:
        denominator = panel.high - panel.low
        temp = ((panel.close - panel.low) - (panel.high - panel.close)) / denominator
        # Old impl was `iloc[-6:, :].sum()` which used skipna=True and returned
        # 0.0 even when all 6 rows were NaN (e.g. limit-up/down with high==low).
        # `rolling.sum` returns NaN in that case, so we fillna(0) on the source
        # to keep the all-NaN window -> 0.0 contract intact.
        return (temp * panel.volume).fillna(0.0).rolling(6).sum()

    def alpha_012(self, panel: Alpha191Panel) -> pd.DataFrame:
        vwap10 = self.ts_mean(panel.vwap, 10)
        part1 = self.rank(panel.open - vwap10)
        part2 = -self.rank((panel.close - panel.vwap).abs())
        return part1 * part2

    def alpha_013(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (panel.high * panel.low) ** 0.5 - panel.vwap

    def alpha_014(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.delta(panel.close, 5)

    def alpha_015(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.open / self.delay(panel.close, 1) - 1.0

    def alpha_016(self, panel: Alpha191Panel) -> pd.DataFrame:
        volume_rank = self.rank(panel.volume)
        vwap_rank = self.rank(panel.vwap)
        corr_value = self.corr(volume_rank, vwap_rank, 5)
        return -self.ts_max(self.rank(corr_value), 5)

    def alpha_017(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = self.rank(panel.vwap - self.ts_max(panel.vwap, 15))
        part2 = self.delta(panel.close, 5)
        return part1**part2

    def alpha_018(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.close / self.delay(panel.close, 5)

    def alpha_019(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_close = self.delay(panel.close, 5)
        lower_branch = ((panel.close - delay_close) / delay_close).where(
            panel.close < delay_close, 0.0
        )
        upper_branch = ((panel.close - delay_close) / panel.close).where(
            panel.close > delay_close, 0.0
        )
        return lower_branch.fillna(0.0) + upper_branch.fillna(0.0)

    def alpha_020(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            (panel.close - self.delay(panel.close, 6))
            * 100.0
            / self.delay(panel.close, 6)
        )

    def alpha_021(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized 6-day linear regression slope via manual rolling stats.
        # slope = cov(x, y) / var(x); x = [1..6] has constant moments.
        mean_close = self.ts_mean(panel.close, 6)
        n = 6.0
        sum_x = n * (n + 1.0) / 2.0  # 21
        sum_x2 = n * (n + 1.0) * (2.0 * n + 1.0) / 6.0  # 91
        denom = sum_x2 - sum_x**2 / n  # = 17.5 (population SSE_x)
        sum_y = mean_close.rolling(6).sum()
        weights = np.arange(1.0, 7.0)
        sum_xy = self._weighted_rolling_sum(mean_close, weights)
        slope = (sum_xy - sum_x * sum_y / n) / denom
        return slope

    def alpha_022(self, panel: Alpha191Panel) -> pd.DataFrame:
        mean_close = self.ts_mean(panel.close, 6)
        ratio = (panel.close - mean_close) / mean_close
        return self.sma(ratio - self.delay(ratio, 3), 12, 1)

    def alpha_023(self, panel: Alpha191Panel) -> pd.DataFrame:
        close_std = self.ts_stddev(panel.close, 20)
        rise_branch = close_std.where(
            panel.close > self.delay(panel.close, 1), 0.0
        ).fillna(0.0)
        fall_branch = close_std.where(
            panel.close <= self.delay(panel.close, 1), 0.0
        ).fillna(0.0)
        up = self.sma(rise_branch, 20, 1)
        down = self.sma(fall_branch, 20, 1)
        return up * 100.0 / (up + down)

    def alpha_024(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.sma(panel.close - self.delay(panel.close, 5), 5, 1)

    def alpha_025(self, panel: Alpha191Panel) -> pd.DataFrame:
        # decay_linear is still per-window Python (slow), but called once over the
        # full panel here instead of once per output date → ~100× win vs old loop.
        delta_rank = self.rank(self.delta(panel.close, 7))
        volume_ratio = panel.volume / self.ts_mean(panel.volume, 20)
        decay_rank = self.rank(self.decay_linear(volume_ratio, 9))
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        sum_rank = self.rank(self.ts_sum(ret, 250))
        return -(delta_rank * (1.0 - decay_rank) * (1.0 + sum_rank))

    def alpha_026(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = self.ts_sum(panel.close, 7) / 7.0 - panel.close
        part2 = self.corr(panel.vwap, self.delay(panel.close, 5), 230)
        return part1 + part2

    def alpha_027(self, panel: Alpha191Panel) -> pd.DataFrame:
        # wma is per-window Python (slow); same one-call-per-panel win as alpha_025.
        ret3 = (
            (panel.close - self.delay(panel.close, 3))
            / self.delay(panel.close, 3)
            * 100.0
        )
        ret6 = (
            (panel.close - self.delay(panel.close, 6))
            / self.delay(panel.close, 6)
            * 100.0
        )
        return self.wma(ret3 + ret6, 12)

    def alpha_028(self, panel: Alpha191Panel) -> pd.DataFrame:
        base = (
            (panel.close - self.ts_min(panel.low, 9))
            / (self.ts_max(panel.high, 9) - self.ts_min(panel.low, 9))
            * 100.0
        )
        sma1 = self.sma(base, 3, 1)
        return 3.0 * sma1 - 2.0 * self.sma(sma1, 3, 1)

    def alpha_029(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            (panel.close - self.delay(panel.close, 6)) / self.delay(panel.close, 6)
        ) * panel.volume

    def alpha_030(self, panel: Alpha191Panel) -> pd.Series:
        raise NotImplementedError(
            "alpha_030 requires MKT/SMB/HML factor inputs, which are not available in the current data sources."
        )

    def alpha_031(self, panel: Alpha191Panel) -> pd.DataFrame:
        mean_close = self.ts_mean(panel.close, 12)
        return (panel.close - mean_close) / mean_close * 100.0

    def alpha_032(self, panel: Alpha191Panel) -> pd.DataFrame:
        corr_value = self.corr(self.rank(panel.high), self.rank(panel.volume), 3)
        return -self.ts_sum(self.rank(corr_value), 3)

    def alpha_033(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        low_min5 = self.ts_min(panel.low, 5)
        left = -low_min5 + self.delay(low_min5, 5)
        middle = self.rank((self.ts_sum(ret, 240) - self.ts_sum(ret, 20)) / 220.0)
        # Vectorized ts_rank via rolling.rank to avoid the per-window Python callback.
        right = panel.volume.rolling(5).rank(pct=True)
        return left * middle * right

    def alpha_034(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.ts_mean(panel.close, 12) / panel.close

    def alpha_035(self, panel: Alpha191Panel) -> pd.DataFrame:
        # decay_linear is still per-window Python (slow), but called once over the
        # full panel instead of once per output date.
        left = self.rank(self.decay_linear(self.delta(panel.open, 1), 15))
        right = self.rank(self.decay_linear(self.corr(panel.volume, panel.open, 17), 7))
        # Old impl: pd.concat([left, right], axis=1).min(axis=1) — pandas .min
        # defaults to skipna=True, so a row with one NaN still returns the other
        # value. Reproduce that with .where to keep partial-NaN cells.
        return -(left.where(~(left > right), right).where(~left.isna(), right))

    def alpha_036(self, panel: Alpha191Panel) -> pd.DataFrame:
        corr_value = self.corr(self.rank(panel.volume), self.rank(panel.vwap), 6)
        return self.rank(self.ts_sum(corr_value, 2))

    def alpha_037(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        signal = self.ts_sum(panel.open, 5) * self.ts_sum(ret, 5)
        return -self.rank(signal - self.delay(signal, 10))

    def alpha_038(self, panel: Alpha191Panel) -> pd.DataFrame:
        condition = (self.ts_sum(panel.high, 20) / 20.0) < panel.high
        return -self.delta(panel.high, 2).where(condition, 0.0)

    def alpha_039(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(self.decay_linear(self.delta(panel.close, 2), 8))
        volume_mean_180 = self.ts_mean(panel.volume, 180)
        corr_input = self.ts_sum(volume_mean_180, 37)
        right = self.rank(
            self.decay_linear(
                self.corr(panel.vwap * 0.3 + panel.open * 0.7, corr_input, 14),
                12,
            )
        )
        return -(left - right)

    def alpha_040(self, panel: Alpha191Panel) -> pd.DataFrame:
        rising_volume = panel.volume.where(
            panel.close > self.delay(panel.close, 1), 0.0
        ).fillna(0.0)
        falling_volume = panel.volume.where(
            panel.close <= self.delay(panel.close, 1), 0.0
        ).fillna(0.0)
        return self.ts_sum(rising_volume, 26) / self.ts_sum(falling_volume, 26) * 100.0

    def alpha_041(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -self.rank(np.maximum(self.delta(panel.vwap, 3), 5.0))

    def alpha_042(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -(
            self.corr(panel.high, panel.volume, 10)
            * self.rank(self.ts_stddev(panel.high, 10))
        )

    def alpha_043(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_close = self.delay(panel.close, 1)
        positive = panel.volume.where(panel.close > delay_close, 0.0).fillna(0.0)
        negative = -panel.volume.where(panel.close < delay_close, 0.0).fillna(0.0)
        return self.ts_sum(positive + negative, 6)

    def alpha_044(self, panel: Alpha191Panel) -> pd.DataFrame:
        # decay_linear (Python callback) called once per panel; outer ts_rank
        # vectorized via rolling.rank to eliminate per-window Python loop.
        decay_left = self.decay_linear(
            self.corr(panel.low, self.ts_mean(panel.volume, 10), 7), 6
        )
        left = decay_left.rolling(4).rank(pct=True)
        decay_right = self.decay_linear(self.delta(panel.vwap, 3), 10)
        right = decay_right.rolling(15).rank(pct=True)
        return left + right

    def alpha_045(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(self.delta(panel.close * 0.6 + panel.open * 0.4, 1))
        right = self.rank(self.corr(panel.vwap, self.ts_mean(panel.volume, 150), 15))
        return left * right

    def alpha_046(self, panel: Alpha191Panel) -> pd.DataFrame:
        mean_combo = (
            self.ts_mean(panel.close, 3)
            + self.ts_mean(panel.close, 6)
            + self.ts_mean(panel.close, 12)
            + self.ts_mean(panel.close, 24)
        ) * 0.25
        return mean_combo / panel.close

    def alpha_047(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = self.ts_max(panel.high, 6) - panel.close
        part2 = self.ts_max(panel.high, 6) - self.ts_min(panel.low, 6)
        return self.ewma(100.0 * part1 / part2, alpha=1.0 / 9)

    def alpha_048(self, panel: Alpha191Panel) -> pd.DataFrame:
        sign_sum = (
            np.sign(panel.close - self.delay(panel.close, 1))
            + np.sign(self.delay(panel.close, 1) - self.delay(panel.close, 2))
            + np.sign(self.delay(panel.close, 2) - self.delay(panel.close, 3))
        )
        return (
            -self.rank(sign_sum)
            * self.ts_sum(panel.volume, 5)
            / self.ts_sum(panel.volume, 20)
        )

    def alpha_049(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_high = self.delay(panel.high, 1)
        delay_low = self.delay(panel.low, 1)
        amplitude = np.maximum(
            (panel.high - delay_high).abs(), (panel.low - delay_low).abs()
        )
        # fillna(0) before rolling.sum to match old iloc[-12:].sum() skipna=True behavior.
        lower = (
            amplitude.where((panel.high + panel.low) < (delay_high + delay_low), 0.0)
            .fillna(0.0)
            .rolling(12)
            .sum()
        )
        upper = (
            amplitude.where((panel.high + panel.low) > (delay_high + delay_low), 0.0)
            .fillna(0.0)
            .rolling(12)
            .sum()
        )
        return lower / (lower + upper)

    def alpha_050(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_high = self.delay(panel.high, 1)
        delay_low = self.delay(panel.low, 1)
        amplitude = np.maximum(
            (panel.high - delay_high).abs(), (panel.low - delay_low).abs()
        )
        up = (
            amplitude.where((panel.high + panel.low) > (delay_high + delay_low), 0.0)
            .fillna(0.0)
            .rolling(12)
            .sum()
        )
        down = (
            amplitude.where((panel.high + panel.low) < (delay_high + delay_low), 0.0)
            .fillna(0.0)
            .rolling(12)
            .sum()
        )
        return (up / (up + down)) - (down / (up + down))

    def alpha_051(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_high = self.delay(panel.high, 1)
        delay_low = self.delay(panel.low, 1)
        amplitude = np.maximum(
            (panel.high - delay_high).abs(), (panel.low - delay_low).abs()
        )
        up = (
            amplitude.where((panel.high + panel.low) > (delay_high + delay_low), 0.0)
            .fillna(0.0)
            .rolling(12)
            .sum()
        )
        down = (
            amplitude.where((panel.high + panel.low) < (delay_high + delay_low), 0.0)
            .fillna(0.0)
            .rolling(12)
            .sum()
        )
        return up / (up + down)

    def alpha_052(self, panel: Alpha191Panel) -> pd.DataFrame:
        typical_prev = self.delay((panel.high + panel.low + panel.close) / 3.0, 1)
        part1 = np.maximum(panel.high - typical_prev, 0.0).rolling(26).sum()
        part2 = np.maximum(typical_prev - panel.low, 0.0).rolling(26).sum()
        return part1 / part2 * 100.0

    def alpha_053(self, panel: Alpha191Panel) -> pd.DataFrame:
        rise = panel.close.where(panel.close > self.delay(panel.close, 1))
        return rise.rolling(12).count() * 100.0 / 12.0

    def alpha_054(self, panel: Alpha191Panel) -> pd.DataFrame:
        diff = panel.close - panel.open
        # H-3:STD(ABS(CLOSE-OPEN), 10)——rolling(10) 与同式 CORR(CLOSE, OPEN, 10)
        # 同窗。旧的全样本 std 使 T 日值包含 T 之后的数据(panel-mode 未来函数)。
        part1 = diff.abs().rolling(10).std()
        part2 = diff
        part3 = panel.close.rolling(10).corr(panel.open)
        return -self.rank(part1 + part2 + part3)

    def alpha_055(self, panel: Alpha191Panel) -> pd.DataFrame:
        prev_close = self.delay(panel.close, 1)
        prev_open = self.delay(panel.open, 1)
        term_num = 16.0 * (
            panel.close
            - prev_close
            + (panel.close - panel.open) / 2.0
            + prev_close
            - prev_open
        )

        a = (panel.high - prev_close).abs()
        b = (panel.low - prev_close).abs()
        c = (panel.high - self.delay(panel.low, 1)).abs()

        option1 = a + b / 2.0 + (prev_close - prev_open).abs() / 4.0
        option2 = b + a / 2.0 + (prev_close - prev_open).abs() / 4.0
        option3 = c + (prev_close - prev_open).abs() / 4.0

        condition1 = (a > b) & (a > c)
        condition2 = (b > c) & (b > a)
        denom = option3.where(~condition2, option2)
        denom = denom.where(~condition1, option1)

        daily = (term_num / denom) * np.maximum(a, b)
        return daily.rolling(20).sum()

    def alpha_056(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = self.rank(panel.open - panel.open.rolling(12).min())
        sum_price = self.ts_sum((panel.high + panel.low) / 2.0, 19)
        sum_volume = self.ts_sum(self.ts_mean(panel.volume, 40), 19)
        corr_value = self.corr(sum_price, sum_volume, 13)
        part2 = self.rank(self.rank(corr_value) ** 5)
        return (part1 < part2).astype(float)

    def alpha_057(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = panel.close - self.ts_min(panel.low, 9)
        part2 = self.ts_max(panel.high, 9) - self.ts_min(panel.low, 9)
        return self.sma(part1 * 100.0 / part2, 3, 1)

    def alpha_058(self, panel: Alpha191Panel) -> pd.DataFrame:
        rise = panel.close.where(panel.close > self.delay(panel.close, 1))
        return rise.rolling(20).count() * 100.0 / 20.0

    def alpha_059(self, panel: Alpha191Panel) -> pd.DataFrame:
        delay_close = self.delay(panel.close, 1)
        value = pd.DataFrame(0.0, index=panel.close.index, columns=panel.close.columns)
        value = value.mask(
            panel.close > delay_close, panel.close - np.minimum(panel.low, delay_close)
        )
        value = value.mask(
            panel.close < delay_close, panel.close - np.maximum(panel.high, delay_close)
        )
        return value.rolling(20).sum()

    def alpha_060(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = (panel.close - panel.low) - (panel.high - panel.close)
        part2 = panel.high - panel.low
        return (panel.volume * part1 / part2).rolling(20).sum()

    def alpha_061(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(self.decay_linear(self.delta(panel.vwap, 1), 12))
        right = self.rank(
            self.decay_linear(
                self.rank(self.corr(panel.low, self.ts_mean(panel.volume, 80), 8)), 17
            )
        )
        # Element-wise maximum
        return -np.fmax(left, right)

    def alpha_062(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -self.corr(panel.high, self.rank(panel.volume), 5)

    def alpha_063(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        up = self.sma(np.maximum(delta, 0.0), 6, 1)
        down = self.sma(delta.abs(), 6, 1)
        return up * 100.0 / down

    def alpha_064(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.decay_linear(
                self.corr(self.rank(panel.vwap), self.rank(panel.volume), 4), 4
            )
        )
        right_input = np.maximum(
            self.corr(
                self.rank(panel.close), self.rank(self.ts_mean(panel.volume, 60)), 4
            ),
            13,
        )
        right = self.rank(self.decay_linear(right_input, 14))
        # Element-wise maximum
        return -np.fmax(left, right)

    def alpha_065(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.ts_mean(panel.close, 6) / panel.close

    def alpha_066(self, panel: Alpha191Panel) -> pd.DataFrame:
        mean6 = self.ts_mean(panel.close, 6)
        return ((panel.close - mean6) / mean6) * 100.0

    def alpha_067(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        up = self.sma(np.maximum(delta, 0.0), 24, 1)
        down = self.sma(delta.abs(), 24, 1)
        return up * 100.0 / down

    def alpha_068(self, panel: Alpha191Panel) -> pd.DataFrame:
        term = (
            (
                ((panel.high + panel.low) / 2.0)
                - ((self.delay(panel.high, 1) + self.delay(panel.low, 1)) / 2.0)
            )
            * (panel.high - panel.low)
            / panel.volume
        )
        return self.sma(term, 15, 2)

    def alpha_069(self, panel: Alpha191Panel) -> pd.DataFrame:
        prev_open = self.delay(panel.open, 1)
        dtm = np.maximum(panel.high - panel.open, panel.open - prev_open).where(
            panel.open > prev_open, 0.0
        )
        dbm = np.maximum(panel.open - panel.low, panel.open - prev_open).where(
            panel.open < prev_open, 0.0
        )
        sum_dtm = self.ts_sum(dtm, 20)
        sum_dbm = self.ts_sum(dbm, 20)

        alpha_df = pd.DataFrame(
            0.0, index=panel.close.index, columns=panel.close.columns
        )
        greater = sum_dtm > sum_dbm
        less = sum_dtm < sum_dbm
        alpha_df = alpha_df.mask(greater, (sum_dtm - sum_dbm) / sum_dtm)
        alpha_df = alpha_df.mask(less, (sum_dtm - sum_dbm) / sum_dbm)
        return alpha_df

    def alpha_070(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.amount.rolling(6).std()

    def alpha_071(self, panel: Alpha191Panel) -> pd.DataFrame:
        mean24 = self.ts_mean(panel.close, 24)
        return _safe_div(panel.close - mean24, mean24) * 100.0

    def alpha_072(self, panel: Alpha191Panel) -> pd.DataFrame:
        data1 = self.ts_max(panel.high, 6) - panel.close
        data2 = self.ts_max(panel.high, 6) - self.ts_min(panel.low, 6)
        return self.sma(_safe_div(data1, data2) * 100.0, 15, 1)

    def alpha_073(self, panel: Alpha191Panel) -> pd.DataFrame:
        left_corr = self.corr(panel.close, panel.volume, 10)
        left = self.ts_rank(self.decay_linear(self.decay_linear(left_corr, 16), 4), 5)
        right_corr = self.corr(panel.vwap, self.ts_mean(panel.volume, 30), 4)
        right = self.rank(self.decay_linear(right_corr, 3))
        return -(left - right)

    def alpha_074(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.corr(
                self.ts_sum(panel.low * 0.35 + panel.vwap * 0.65, 20),
                self.ts_sum(self.ts_mean(panel.volume, 40), 20),
                7,
            )
        )
        right = self.rank(self.corr(self.rank(panel.vwap), self.rank(panel.volume), 6))
        return left + right

    def alpha_075(self, panel: Alpha191Panel) -> pd.DataFrame:
        if panel.benchmark_open is None or panel.benchmark_close is None:
            raise ValueError(
                "alpha_075 requires benchmark_open and benchmark_close series."
            )
        bench_down = panel.benchmark_close < panel.benchmark_open

        stock_up = panel.close > panel.open
        count = stock_up.mul(bench_down, axis=0).rolling(50).sum()

        denominator = bench_down.rolling(50).sum()
        return count.div(denominator, axis=0)

    def alpha_076(self, panel: Alpha191Panel) -> pd.DataFrame:
        ratio = ((panel.close / self.delay(panel.close, 1) - 1.0).abs()) / panel.volume
        return self.ts_stddev(ratio, 20) / self.ts_mean(ratio, 20)

    def alpha_077(self, panel: Alpha191Panel) -> pd.DataFrame:
        left_input = ((panel.high + panel.low) / 2.0 + panel.high) - (
            panel.vwap + panel.high
        )
        left = self.rank(self.decay_linear(left_input, 20))
        right = self.rank(
            self.decay_linear(
                self.corr(
                    (panel.high + panel.low) / 2.0, self.ts_mean(panel.volume, 40), 3
                ),
                6,
            )
        )
        # Element-wise minimum (fmin: single-NaN → take non-NaN side, matching pandas skipna)
        return np.fmin(left, right)

    def alpha_078(self, panel: Alpha191Panel) -> pd.DataFrame:
        typical = (panel.high + panel.low + panel.close) / 3.0
        mean12 = self.ts_mean(typical, 12)
        denom = 0.015 * self.ts_mean((panel.close - mean12).abs(), 12)
        return (typical - mean12) / denom

    def alpha_079(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        return (
            self.sma(np.maximum(delta, 0.0), 12, 1)
            / self.sma(delta.abs(), 12, 1)
            * 100.0
        )

    def alpha_080(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            _safe_div(
                panel.volume - self.delay(panel.volume, 5),
                self.delay(panel.volume, 5),
            )
            * 100.0
        )

    def alpha_081(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.ewma(panel.volume, alpha=2.0 / 21)

    def alpha_082(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = self.ts_max(panel.high, 6) - panel.close
        part2 = self.ts_max(panel.high, 6) - self.ts_min(panel.low, 6)
        return self.ewma(_safe_div(part1, part2) * 100.0, alpha=1.0 / 20)

    def alpha_083(self, panel: Alpha191Panel) -> pd.DataFrame:
        cov = self.rank(panel.high).rolling(5).cov(self.rank(panel.volume))
        return -self.rank(cov)

    def alpha_084(self, panel: Alpha191Panel) -> pd.DataFrame:
        up = panel.volume.where(panel.close > self.delay(panel.close, 1), 0.0).fillna(
            0.0
        )
        down = -panel.volume.where(
            panel.close < self.delay(panel.close, 1), 0.0
        ).fillna(0.0)
        return (up + down).rolling(20).sum()

    def alpha_085(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.ts_rank(panel.volume / self.ts_mean(panel.volume, 20), 20)
        right = self.ts_rank(-self.delta(panel.close, 7), 8)
        return left * right

    def alpha_086(self, panel: Alpha191Panel) -> pd.DataFrame:
        temp = (self.delay(panel.close, 20) - self.delay(panel.close, 10)) / 10.0 - (
            self.delay(panel.close, 10) - panel.close
        ) / 10.0
        result = pd.DataFrame(
            -1.0, index=panel.close.index, columns=panel.close.columns
        )
        result = result.mask(temp < 0, 1.0)
        result = result.mask(
            (temp <= 0.25) & (temp >= 0), -(panel.close - self.delay(panel.close, 1))
        )
        return result

    def alpha_087(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(self.decay_linear(self.delta(panel.vwap, 4), 7))
        ratio = (panel.low - panel.vwap) / (
            panel.open - ((panel.high + panel.low) * 0.5)
        )
        right = self.ts_rank(self.decay_linear(ratio, 11), 7)
        return -(left + right)

    def alpha_088(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            (panel.close - self.delay(panel.close, 20)) / self.delay(panel.close, 20)
        ) * 100.0

    def alpha_089(self, panel: Alpha191Panel) -> pd.DataFrame:
        sma13 = self.sma(panel.close, 13, 2)
        sma27 = self.sma(panel.close, 27, 2)
        return 2.0 * (sma13 - sma27 - self.sma(sma13 - sma27, 10, 2))

    def alpha_090(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -self.rank(self.corr(self.rank(panel.vwap), self.rank(panel.volume), 5))

    def alpha_091(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(panel.close - self.ts_max(panel.close, 5))
        right = self.rank(self.corr(self.ts_mean(panel.volume, 40), panel.low, 5))
        return left * right - 1.0

    def alpha_092(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.decay_linear(self.delta(panel.close * 0.35 + panel.vwap * 0.65, 2), 3)
        )
        corr_abs = self.corr(self.ts_mean(panel.volume, 180), panel.close, 13).abs()
        right = self.ts_rank(self.decay_linear(corr_abs, 5), 15)
        # Element-wise maximum
        return -np.fmax(left, right)

    def alpha_093(self, panel: Alpha191Panel) -> pd.DataFrame:
        cond = panel.open >= self.delay(panel.open, 1)
        choice = np.maximum(
            panel.open - panel.low, panel.open - self.delay(panel.open, 1)
        )
        return choice.where(~cond, 0.0).rolling(20).sum()

    def alpha_094(self, panel: Alpha191Panel) -> pd.DataFrame:
        prev_close = self.delay(panel.close, 1)
        value = pd.DataFrame(0.0, index=panel.close.index, columns=panel.close.columns)
        value = value.mask(panel.close > prev_close, panel.volume)
        value = value.mask(panel.close < prev_close, -panel.volume)
        return value.rolling(30).sum()

    def alpha_095(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.amount.rolling(20).std()

    def alpha_096(self, panel: Alpha191Panel) -> pd.DataFrame:
        base = (
            100.0
            * (panel.close - self.ts_min(panel.low, 9))
            / (self.ts_max(panel.high, 9) - self.ts_min(panel.low, 9))
        )
        return self.sma(self.sma(base, 3, 1), 3, 1)

    def alpha_097(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.volume.rolling(10).std()

    def alpha_098(self, panel: Alpha191Panel) -> pd.DataFrame:
        mean100 = self.ts_mean(panel.close, 100)
        cond = (self.delta(mean100, 100) / self.delay(panel.close, 100)) <= 0.05
        left = -(panel.close - self.ts_min(panel.close, 100))
        right = -self.delta(panel.close, 3)
        return right.where(~cond, left)

    def alpha_099(self, panel: Alpha191Panel) -> pd.DataFrame:
        cov = self.rank(panel.close).rolling(5).cov(self.rank(panel.volume))
        return -self.rank(cov)

    def alpha_100(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.volume.rolling(20).std()

    def alpha_101(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(
            self.corr(panel.close, self.ts_sum(self.ts_mean(panel.volume, 30), 37), 15)
        )
        rank2 = self.rank(
            self.corr(
                self.rank(panel.high * 0.1 + panel.vwap * 0.9),
                self.rank(panel.volume),
                11,
            )
        )
        return -(rank1 < rank2).astype(float)

    def alpha_102(self, panel: Alpha191Panel) -> pd.DataFrame:
        vol_delta = panel.volume - self.delay(panel.volume, 1)
        return (
            self.sma(np.maximum(vol_delta, 0.0), 6, 1)
            / self.sma(vol_delta.abs(), 6, 1)
            * 100.0
        )

    def alpha_103(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized argmin-position from window end over rolling(20).
        # Uses stride_tricks to create a (T-19, 20, N) view, then np.argmin(axis=1).
        window = 20
        low = panel.low
        values = low.to_numpy(dtype=float)  # (T, N)
        n_rows, n_cols = values.shape
        result = np.full_like(values, np.nan)
        if n_rows < window:
            return pd.DataFrame(result, index=low.index, columns=low.columns)
        # Build sliding windows via stride_tricks
        windows = sliding_window_view(values, window, axis=0)  # (T-19, N, 20)
        # argmin along last axis (the window dimension);NaN 窗口 → NaN
        argmin_pos = _nan_safe_arg_reduce(windows, "min")  # (T-19, N)
        out_vals = np.where(
            argmin_pos >= 0, (argmin_pos + 1) / float(window) * 100.0, np.nan
        )
        result[window - 1 :] = out_vals
        return pd.DataFrame(result, index=low.index, columns=low.columns)

    def alpha_104(self, panel: Alpha191Panel) -> pd.DataFrame:
        corr = self.corr(panel.high, panel.volume, 5)
        return -(self.delta(corr, 5) * self.rank(self.ts_stddev(panel.close, 20)))

    def alpha_105(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -self.corr(self.rank(panel.open), self.rank(panel.volume), 10)

    def alpha_106(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.delta(panel.close, 20)

    def alpha_107(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = -self.rank(panel.open - self.delay(panel.high, 1))
        rank2 = self.rank(panel.open - self.delay(panel.close, 1))
        rank3 = self.rank(panel.open - self.delay(panel.low, 1))
        return rank1 * rank2 * rank3

    def alpha_108(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(panel.high - self.ts_min(panel.high, 2))
        rank2 = self.rank(self.corr(panel.vwap, self.ts_mean(panel.volume, 120), 6))
        return -(rank1**rank2)

    def alpha_109(self, panel: Alpha191Panel) -> pd.DataFrame:
        spread = panel.high - panel.low
        sma1 = self.sma(spread, 10, 2)
        sma2 = self.sma(sma1, 10, 2)
        return sma1 / sma2

    def alpha_110(self, panel: Alpha191Panel) -> pd.DataFrame:
        up = np.maximum(panel.high - self.delay(panel.close, 1), 0.0)
        down = np.maximum(self.delay(panel.close, 1) - panel.low, 0.0)
        return self.ts_sum(up, 20) / self.ts_sum(down, 20) * 100.0

    def alpha_111(self, panel: Alpha191Panel) -> pd.DataFrame:
        data = (
            panel.volume
            * ((panel.close - panel.low) - (panel.high - panel.close))
            / (panel.high - panel.low)
        )
        return self.sma(data, 11, 2) - self.sma(data, 4, 2)

    def alpha_112(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        pos = self.ts_sum(delta.where(delta > 0, 0.0), 12)
        neg = self.ts_sum((-delta.where(delta < 0, 0.0)), 12)
        return ((pos - neg) / (pos + neg)) * 100.0

    def alpha_113(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(self.ts_mean(self.delay(panel.close, 5), 20))
        corr1 = self.corr(panel.close, panel.volume, 2)
        rank2 = self.rank(
            self.corr(self.ts_sum(panel.close, 5), self.ts_sum(panel.close, 20), 2)
        )
        return -(rank1 * corr1 * rank2)

    def alpha_114(self, panel: Alpha191Panel) -> pd.DataFrame:
        data1 = (panel.high - panel.low) / self.ts_mean(panel.close, 5)
        rank1 = self.rank(self.delay(data1, 2))
        rank2 = self.rank(self.rank(panel.volume))
        denom = data1 / (panel.vwap - panel.close)
        return (rank1 * rank2) / denom

    def alpha_115(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(
            self.corr(
                panel.high * 0.9 + panel.close * 0.1, self.ts_mean(panel.volume, 30), 10
            )
        )
        rank2 = self.rank(
            self.corr(
                self.ts_rank((panel.high + panel.low) / 2.0, 4),
                self.ts_rank(panel.volume, 10),
                7,
            )
        )
        return rank1**rank2

    def alpha_116(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized 20-day linear regression slope via rolling stats.
        # slope = cov(x,y) / var(x); x = [1..20] has constant var and cov(x,sum_y).
        n = 20.0
        x_mean = n * (n + 1.0) / 2.0 / n  # 10.5
        x_var = (
            n * (n + 1.0) * (2.0 * n + 1.0) / 6.0 - n * x_mean**2
        ) / n  # population var
        weights = np.arange(1.0, 21.0)
        sum_xy = self._weighted_rolling_sum(panel.close, weights)
        sum_y = panel.close.rolling(20).sum()
        slope = (sum_xy / n - x_mean * sum_y / n) / x_var
        return slope

    def alpha_117(self, panel: Alpha191Panel) -> pd.DataFrame:
        part1 = self.ts_rank(panel.volume, 32)
        part2 = 1.0 - self.ts_rank(panel.close + panel.high - panel.low, 16)
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        part3 = 1.0 - self.ts_rank(ret, 32)
        return part1 * part2 * part3

    def alpha_118(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            self.ts_sum(panel.high - panel.open, 20)
            / self.ts_sum(panel.open - panel.low, 20)
            * 100.0
        )

    def alpha_119(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.decay_linear(
                self.corr(
                    panel.vwap, self.ts_sum(self.ts_mean(panel.volume, 5), 26), 5
                ),
                7,
            )
        )
        right = self.rank(
            self.decay_linear(
                self.ts_rank(
                    self.ts_min(
                        self.corr(
                            self.rank(panel.open),
                            self.rank(self.ts_mean(panel.volume, 15)),
                            21,
                        ),
                        9,
                    ),
                    7,
                ),
                8,
            )
        )
        return left - right

    def alpha_120(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.rank(panel.vwap - panel.close) / self.rank(panel.vwap + panel.close)

    def alpha_121(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(panel.vwap - self.ts_min(panel.vwap, 12))
        tsrank_vwap = self.ts_rank(panel.vwap, 20)
        tsrank_vol = self.ts_rank(self.ts_mean(panel.volume, 60), 2)
        right = self.ts_rank(self.corr(tsrank_vwap, tsrank_vol, 18), 3)
        return -(left**right)

    def alpha_122(self, panel: Alpha191Panel) -> pd.DataFrame:
        # P-2:delay(smooth) 可为 0(前段 log 恒 0 的三重 SMA),x/0 → ±inf
        # 会污染下游 rank——统一走 _safe_div 置 NaN。
        log_close = np.log(panel.close.where(panel.close > 0))
        smooth = self.sma(self.sma(self.sma(log_close, 13, 2), 13, 2), 13, 2)
        return _safe_div(smooth - self.delay(smooth, 1), self.delay(smooth, 1))

    def alpha_123(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.corr(
                self.ts_sum((panel.high + panel.low) / 2.0, 20),
                self.ts_sum(self.ts_mean(panel.volume, 60), 20),
                9,
            )
        )
        right = self.rank(self.corr(panel.low, panel.volume, 6))
        return -(left < right).astype(float)

    def alpha_124(self, panel: Alpha191Panel) -> pd.DataFrame:
        denom = self.decay_linear(self.rank(self.ts_max(panel.close, 30)), 2)
        return (panel.close - panel.vwap) / denom

    def alpha_125(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.decay_linear(
                self.corr(panel.vwap, self.ts_mean(panel.volume, 80), 17), 20
            )
        )
        right = self.rank(
            self.decay_linear(self.delta(panel.close * 0.5 + panel.vwap * 0.5, 3), 16)
        )
        return left / right

    def alpha_126(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (panel.close + panel.high + panel.low) / 3.0

    def alpha_127(self, panel: Alpha191Panel) -> pd.DataFrame:
        drawdown = (
            100.0
            * (panel.close - self.ts_max(panel.close, 12))
            / self.ts_max(panel.close, 12)
        )
        return self.ts_mean(drawdown**2, 12) ** 0.5

    def alpha_128(self, panel: Alpha191Panel) -> pd.DataFrame:
        typical = (panel.high + panel.low + panel.close) / 3.0
        prev_typical = self.delay(typical, 1)
        pos_flow = self.ts_sum(
            (typical * panel.volume).where(typical > prev_typical, 0.0), 14
        )
        neg_flow = self.ts_sum(
            (typical * panel.volume).where(typical < prev_typical, 0.0), 14
        )
        money_ratio = pos_flow / neg_flow
        return 100.0 - (100.0 / (1.0 + money_ratio))

    def alpha_129(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = self.delta(panel.close, 1)
        return (-delta.where(delta < 0, 0.0)).rolling(12).sum()

    def alpha_130(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.decay_linear(
                self.corr(
                    (panel.high + panel.low) / 2.0, self.ts_mean(panel.volume, 40), 9
                ),
                10,
            )
        )
        right = self.rank(
            self.decay_linear(
                self.corr(self.rank(panel.vwap), self.rank(panel.volume), 7), 3
            )
        )
        return left / right

    def alpha_131(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(self.delta(panel.vwap, 1))
        right = self.ts_rank(
            self.corr(panel.close, self.ts_mean(panel.volume, 50), 18), 18
        )
        return left**right

    def alpha_132(self, panel: Alpha191Panel) -> pd.DataFrame:
        return panel.amount.rolling(20).mean()

    def alpha_133(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized: highday = rolling(20) argmax position from end, lowday = argmin.
        window = 20
        high_vals = panel.high.to_numpy(dtype=float)
        low_vals = panel.low.to_numpy(dtype=float)
        n_rows, n_cols = high_vals.shape
        result = np.full_like(high_vals, np.nan)
        if n_rows >= window:
            high_wins = sliding_window_view(high_vals, window, axis=0)
            low_wins = sliding_window_view(low_vals, window, axis=0)
            highday = _nan_safe_arg_reduce(high_wins, "max")  # (T-19, N)
            lowday = _nan_safe_arg_reduce(low_wins, "min")
            valid = (highday >= 0) & (lowday >= 0)
            result[window - 1 :] = np.where(
                valid,
                ((highday + 1) / float(window) - (lowday + 1) / float(window)) * 100.0,
                np.nan,
            )
        return pd.DataFrame(
            result, index=panel.close.index, columns=panel.close.columns
        )

    def alpha_134(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            (panel.close - self.delay(panel.close, 12)) / self.delay(panel.close, 12)
        ) * panel.volume

    def alpha_135(self, panel: Alpha191Panel) -> pd.DataFrame:
        data = self.delay(panel.close / self.delay(panel.close, 20), 1)
        return -self.sma(data, 20, 1)

    def alpha_136(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        left = -self.rank(self.delta(ret, 3))
        right = self.corr(panel.open, panel.volume, 10)
        return left * right

    def alpha_137(self, panel: Alpha191Panel) -> pd.DataFrame:
        prev_close = self.delay(panel.close, 1)
        prev_open = self.delay(panel.open, 1)
        term_num = 16.0 * (
            panel.close
            - prev_close
            + (panel.close - panel.open) / 2.0
            + prev_close
            - prev_open
        )

        a = (panel.high - prev_close).abs()
        b = (panel.low - prev_close).abs()
        c = (panel.high - self.delay(panel.low, 1)).abs()

        option1 = a + b / 2.0 + (prev_close - prev_open).abs() / 4.0
        option2 = b + a / 2.0 + (prev_close - prev_open).abs() / 4.0
        option3 = c + (prev_close - prev_open).abs() / 4.0

        condition1 = (a > b) & (a > c)
        condition2 = (b > c) & (b > a)
        denom = option3.where(~condition2, option2)
        denom = denom.where(~condition1, option1)

        return (term_num / denom) * np.maximum(a, b)

    def alpha_138(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = self.rank(
            self.decay_linear(self.delta(panel.low * 0.7 + panel.vwap * 0.3, 3), 20)
        )
        rank_low = self.ts_rank(panel.low, 8)
        rank_vol = self.ts_rank(self.ts_mean(panel.volume, 60), 17)
        corr_value = self.corr(rank_low, rank_vol, 5)
        right = self.ts_rank(self.decay_linear(self.ts_rank(corr_value, 19), 16), 7)
        return -(left - right)

    def alpha_139(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -self.corr(panel.open, panel.volume, 10)

    def alpha_140(self, panel: Alpha191Panel) -> pd.DataFrame:
        left_input = (
            self.rank(panel.open)
            + self.rank(panel.low)
            - self.rank(panel.high)
            - self.rank(panel.close)
        )
        left = self.rank(self.decay_linear(left_input, 8))
        close_rank = self.ts_rank(panel.close, 8)
        volume_rank = self.ts_rank(self.ts_mean(panel.volume, 60), 20)
        corr_value = self.corr(close_rank, volume_rank, 8)
        right = self.ts_rank(self.decay_linear(corr_value, 7), 3)
        # Element-wise minimum (fmin: single-NaN → take non-NaN side)
        return np.fmin(left, right)

    def alpha_141(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -self.rank(
            self.corr(
                self.rank(panel.high), self.rank(self.ts_mean(panel.volume, 15)), 9
            )
        )

    def alpha_142(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(self.ts_rank(panel.close, 10))
        rank2 = self.rank(self.delta(self.delta(panel.close, 1), 1))
        rank3 = self.rank(
            self.ts_rank(panel.volume / self.ts_mean(panel.volume, 20), 5)
        )
        return -(rank1 * rank2 * rank3)

    def alpha_143(self, panel: Alpha191Panel) -> pd.Series:
        raise NotImplementedError(
            "alpha_143 depends on recursive SELF state in the legacy formula and needs a verified non-recursive definition before coding."
        )

    def alpha_144(self, panel: Alpha191Panel) -> pd.DataFrame:
        prev_close = self.delay(panel.close, 1)
        condition = panel.close < prev_close
        numerator = (
            (((panel.close / prev_close) - 1.0).abs() / panel.amount)
            .where(condition, 0.0)
            .fillna(0.0)
            .rolling(20)
            .sum()
        )
        denominator = condition.astype(float).rolling(20).sum()
        return numerator / denominator

    def alpha_145(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            (self.ts_mean(panel.volume, 9) - self.ts_mean(panel.volume, 26))
            / self.ts_mean(panel.volume, 12)
            * 100.0
        )

    def alpha_146(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        smooth = self.sma(ret, 61, 2)
        centered = ret - smooth
        return self.ts_mean(centered, 20) * centered / self.sma(smooth**2, 60, 2)

    def alpha_147(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized 12-day linear regression slope of ts_mean(close,12).
        n = 12.0
        x_mean = n * (n + 1.0) / 2.0 / n
        x_var = (n * (n + 1.0) * (2.0 * n + 1.0) / 6.0 - n * x_mean**2) / n
        weights = np.arange(1.0, 13.0)
        mean_close = self.ts_mean(panel.close, 12)
        sum_xy = self._weighted_rolling_sum(mean_close, weights)
        sum_y = mean_close.rolling(12).sum()
        return (sum_xy / n - x_mean * sum_y / n) / x_var

    def alpha_148(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(
            self.corr(panel.open, self.ts_sum(self.ts_mean(panel.volume, 60), 9), 6)
        )
        rank2 = self.rank(panel.open - self.ts_min(panel.open, 14))
        return -(rank1 < rank2).astype(float)

    def alpha_149(self, panel: Alpha191Panel) -> pd.Series:
        if panel.benchmark_close is None:
            raise ValueError("alpha_149 requires benchmark_close series.")
        stock_ret = panel.close / self.delay(panel.close, 1) - 1.0
        benchmark_ret = panel.benchmark_close / panel.benchmark_close.shift(1) - 1.0
        cond = panel.benchmark_close < panel.benchmark_close.shift(1)
        y = stock_ret.where(cond, np.nan).iloc[-252:, :].to_numpy(dtype=float)
        x = benchmark_ret.where(cond).iloc[-252:].to_numpy(dtype=float)

        # Per-column beta = cov(x, y) / var(x) over the pairwise-valid rows,
        # vectorized across all stocks at once.
        m = ~np.isnan(x)[:, None] & ~np.isnan(y)
        cnt = m.sum(axis=0)
        xv = np.where(m, x[:, None], 0.0)
        yv = np.where(m, y, 0.0)
        safe_cnt = np.where(cnt > 0, cnt, 1)
        xbar = xv.sum(axis=0) / safe_cnt
        ybar = yv.sum(axis=0) / safe_cnt
        dx = np.where(m, x[:, None] - xbar, 0.0)
        dy = np.where(m, y - ybar, 0.0)
        varx = (dx * dx).sum(axis=0)
        cov = (dx * dy).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = np.where((cnt >= 2) & (varx != 0), cov / np.where(varx == 0, np.nan, varx), np.nan)
        alpha = pd.Series(beta, index=panel.close.columns)
        alpha.name = panel.close.index[-1]
        return alpha

    def alpha_150(self, panel: Alpha191Panel) -> pd.DataFrame:
        return ((panel.close + panel.high + panel.low) / 3.0) * panel.volume

    def alpha_151(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.sma(panel.close - self.delay(panel.close, 20), 20, 1)

    def alpha_152(self, panel: Alpha191Panel) -> pd.DataFrame:
        data = self.sma(self.delay(panel.close / self.delay(panel.close, 9), 1), 9, 1)
        return self.sma(
            self.ts_mean(self.delay(data, 1), 12)
            - self.ts_mean(self.delay(data, 1), 26),
            9,
            1,
        )

    def alpha_153(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            self.ts_mean(panel.close, 3)
            + self.ts_mean(panel.close, 6)
            + self.ts_mean(panel.close, 12)
            + self.ts_mean(panel.close, 24)
        ) / 4.0

    def alpha_154(self, panel: Alpha191Panel) -> pd.DataFrame:
        left = panel.vwap - self.ts_min(panel.vwap, 16)
        right = self.corr(panel.vwap, self.ts_mean(panel.volume, 180), 18)
        return (left < right).astype(float)

    def alpha_155(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            self.sma(panel.volume, 13, 2)
            - self.sma(panel.volume, 27, 2)
            - self.sma(
                self.sma(panel.volume, 13, 2) - self.sma(panel.volume, 27, 2), 10, 2
            )
        )

    def alpha_156(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(self.decay_linear(self.delta(panel.vwap, 5), 3))
        base = panel.open * 0.15 + panel.low * 0.85
        rank2 = self.rank(self.decay_linear((self.delta(base, 2) / base) - 1.0, 3))
        # Element-wise maximum (fmax: single-NaN → take non-NaN side)
        return np.fmax(rank1, rank2) - 1.0

    def alpha_157(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(self.rank(-self.rank(self.delta(panel.close - 1.0, 5))))
        min_part = self.ts_min(rank1, 2)
        log_part = np.log(min_part.where(min_part > 0))
        first_term = self.ts_min(self.rank(self.rank(log_part)), 5)
        tsrank_part = self.ts_rank(
            self.delay(-(panel.close / self.delay(panel.close, 1) - 1.0), 6), 5
        )
        return first_term + tsrank_part

    def alpha_158(self, panel: Alpha191Panel) -> pd.DataFrame:
        sma_close = self.sma(panel.close, 15, 2)
        return ((panel.high - sma_close) - (panel.low - sma_close)) / panel.close

    def alpha_159(self, panel: Alpha191Panel) -> pd.DataFrame:
        prev_close = self.delay(panel.close, 1)
        min_base = pd.concat([panel.low, prev_close], axis=0).groupby(level=0).min()
        max_base = pd.concat([panel.high, prev_close], axis=0).groupby(level=0).max()
        term6 = (
            (
                (panel.close - self.ts_sum(min_base, 6))
                / self.ts_sum(max_base - min_base, 6)
            )
            * 12
            * 24
        )
        term12 = (
            (
                (panel.close - self.ts_sum(min_base, 12))
                / self.ts_sum(max_base - min_base, 12)
            )
            * 6
            * 24
        )
        term24 = (
            (
                (panel.close - self.ts_sum(min_base, 24))
                / self.ts_sum(max_base - min_base, 24)
            )
            * 6
            * 24
        )
        return (term6 + term12 + term24) * 100.0 / (6 * 12 + 12 * 24 + 6 * 24)

    def alpha_160(self, panel: Alpha191Panel) -> pd.DataFrame:
        std20 = self.ts_stddev(panel.close, 20)
        return self.sma(
            std20.where(panel.close <= self.delay(panel.close, 1), 0.0), 20, 1
        )

    def alpha_161(self, panel: Alpha191Panel) -> pd.DataFrame:
        tr = np.maximum(
            np.maximum(
                panel.high - panel.low, (self.delay(panel.close, 1) - panel.high).abs()
            ),
            (self.delay(panel.close, 1) - panel.low).abs(),
        )
        return self.ts_mean(tr, 12)

    def alpha_162(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        ratio = (
            self.sma(np.maximum(delta, 0.0), 12, 1)
            / self.sma(delta.abs(), 12, 1)
            * 100.0
        )
        return (ratio - self.ts_min(ratio, 12)) / (
            self.ts_max(ratio, 12) - self.ts_min(ratio, 12)
        )

    def alpha_163(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        return self.rank(
            (-ret)
            * self.ts_mean(panel.volume, 20)
            * panel.vwap
            * (panel.high - panel.close)
        )

    def alpha_164(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        base = pd.DataFrame(
            np.where(
                panel.close > self.delay(panel.close, 1),
                1.0 / delta.replace(0, np.nan),
                1.0,
            ),
            index=panel.close.index,
            columns=panel.close.columns,
        )
        core = (base - self.ts_min(base, 12)) / (panel.high - panel.low) * 100.0
        return self.sma(core, 13, 2)

    def alpha_165(self, panel: Alpha191Panel) -> pd.DataFrame:
        centered = panel.close - self.ts_mean(panel.close, 48)
        # cumsum(x)[-1] over a window is just the window sum
        sumac = centered.rolling(48).sum()
        return (self.ts_max(sumac, 48) - self.ts_min(sumac, 48)) / self.ts_stddev(
            panel.close, 48
        )

    def alpha_166(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret = panel.close / self.delay(panel.close, 1) - 1.0
        mean20 = self.ts_mean(ret, 20)
        centered = ret - mean20
        numerator = self.ts_sum(centered**3, 20)
        denominator = (20 - 1) * (20 - 2) * (self.ts_sum(centered**2, 20) ** 1.5)
        return -(20 * ((20 - 1) ** 1.5)) * numerator / denominator

    def alpha_167(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        return self.ts_sum(delta.where(delta > 0, 0.0), 12)

    def alpha_168(self, panel: Alpha191Panel) -> pd.DataFrame:
        return -(panel.volume / self.ts_mean(panel.volume, 20))

    def alpha_169(self, panel: Alpha191Panel) -> pd.DataFrame:
        delta = panel.close - self.delay(panel.close, 1)
        smooth = self.sma(delta, 9, 1)
        return self.sma(
            self.ts_mean(self.delay(smooth, 1), 12)
            - self.ts_mean(self.delay(smooth, 1), 26),
            10,
            1,
        )

    def alpha_170(self, panel: Alpha191Panel) -> pd.DataFrame:
        x = (self.rank(1.0 / panel.close) * panel.volume) / self.ts_mean(
            panel.volume, 20
        )
        y = (panel.high * self.rank(panel.high - panel.close)) / self.ts_mean(
            panel.high, 5
        )
        z = self.rank(panel.vwap - self.delay(panel.vwap, 5))
        return x * y - z

    def alpha_171(self, panel: Alpha191Panel) -> pd.DataFrame:
        return ((panel.low - panel.close) * (panel.open**5) * -1.0) / (
            (panel.close - panel.high) * (panel.close**5)
        )

    def alpha_172(self, panel: Alpha191Panel) -> pd.DataFrame:
        hd = panel.high - self.delay(panel.high, 1)
        ld = self.delay(panel.low, 1) - panel.low
        tr = np.maximum(
            np.maximum(
                panel.high - panel.low, (panel.high - self.delay(panel.close, 1)).abs()
            ),
            (panel.low - self.delay(panel.close, 1)).abs(),
        )
        sum_tr14 = self.ts_sum(tr, 14)
        sum1 = self.ts_sum(ld.where((ld > 0) & (ld > hd), 0.0), 14) * 100.0 / sum_tr14
        sum2 = self.ts_sum(hd.where((hd > 0) & (hd > ld), 0.0), 14) * 100.0 / sum_tr14
        return self.ts_mean(((sum1 - sum2).abs() / (sum1 + sum2) * 100.0), 6)

    def alpha_173(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            3 * self.sma(panel.close, 13, 2)
            - 2 * self.sma(self.sma(panel.close, 13, 2), 13, 2)
            + self.sma(
                self.sma(
                    self.sma(np.log(panel.close.where(panel.close > 0)), 13, 2), 13, 2
                ),
                13,
                2,
            )
        )

    def alpha_174(self, panel: Alpha191Panel) -> pd.DataFrame:
        std20 = self.ts_stddev(panel.close, 20)
        return self.sma(
            std20.where(panel.close > self.delay(panel.close, 1), 0.0), 20, 1
        )

    def alpha_175(self, panel: Alpha191Panel) -> pd.DataFrame:
        tr = np.maximum(
            np.maximum(
                panel.high - panel.low, (self.delay(panel.close, 1) - panel.high).abs()
            ),
            (self.delay(panel.close, 1) - panel.low).abs(),
        )
        return self.ts_mean(tr, 6)

    def alpha_176(self, panel: Alpha191Panel) -> pd.DataFrame:
        data1 = (panel.close - self.ts_min(panel.low, 12)) / (
            self.ts_max(panel.high, 12) - self.ts_min(panel.low, 12)
        )
        return self.corr(self.rank(data1), self.rank(panel.volume), 6)

    def alpha_177(self, panel: Alpha191Panel) -> pd.DataFrame:
        # Vectorized: rolling(20) argmax position from window end.
        window = 20
        high_vals = panel.high.to_numpy(dtype=float)
        n_rows, n_cols = high_vals.shape
        result = np.full_like(high_vals, np.nan)
        if n_rows >= window:
            windows = sliding_window_view(high_vals, window, axis=0)
            highday = _nan_safe_arg_reduce(windows, "max")
            result[window - 1 :] = np.where(
                highday >= 0, (highday + 1) / float(window) * 100.0, np.nan
            )
        return pd.DataFrame(
            result, index=panel.close.index, columns=panel.close.columns
        )

    def alpha_178(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            (panel.close - self.delay(panel.close, 1)) / self.delay(panel.close, 1)
        ) * panel.volume

    def alpha_179(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(self.corr(panel.vwap, panel.volume, 4))
        rank2 = self.rank(
            self.corr(
                self.rank(panel.low), self.rank(self.ts_mean(panel.volume, 50)), 12
            )
        )
        return rank1 * rank2

    def alpha_180(self, panel: Alpha191Panel) -> pd.DataFrame:
        cond = self.ts_mean(panel.volume, 20) < panel.volume
        delta7 = self.delta(panel.close, 7)
        sign = np.sign(delta7)
        tsrank = self.ts_rank(delta7.abs(), 60)
        left = -tsrank * sign
        right = -panel.volume
        return right.where(~cond, left)

    def alpha_181(self, panel: Alpha191Panel) -> pd.DataFrame:
        """
        alpha_181: 计算股票收益与基准收益之间的某种关系

        公式: SUM(((CLOSE/DELAY(CLOSE,1)-1)-MEAN(...,20))-(BENCHMARK-MEAN(BENCHMARK,20))^2,20)
              / SUM((BENCHMARK-MEAN(BENCHMARK,20))^3)

        注意：这里 BENCHMARK 指的是基准收盘价（不是收益率）
        """
        if panel.benchmark_close is None:
            raise ValueError("alpha_181 requires benchmark_close series.")

        # 股票收益率
        stock_ret = panel.close / self.delay(panel.close, 1) - 1.0
        # 股票收益率中心化
        stock_centered = stock_ret - self.ts_mean(stock_ret, 20)

        # 基准价格中心化（注意：这里用的是价格，不是收益率）
        benchmark_centered = (
            panel.benchmark_close - panel.benchmark_close.rolling(20).mean()
        )
        bench_sq = benchmark_centered**2
        bench_cube = benchmark_centered**3

        # 分子: (股票收益率中心化 - 基准价格中心化的平方) 的 20 日和
        numerator = (stock_centered.sub(bench_sq, axis=0)).rolling(20).sum()
        # 分母: 基准价格中心化的立方的 20 日和（一维 rolling，按行广播）
        denominator = bench_cube.rolling(20).sum()

        return numerator.div(denominator, axis=0)

    def alpha_182(self, panel: Alpha191Panel) -> pd.DataFrame:
        if panel.benchmark_open is None or panel.benchmark_close is None:
            raise ValueError(
                "alpha_182 requires benchmark_open and benchmark_close series."
            )

        cond_stock_up = panel.close > panel.open
        cond_benchmark_up = panel.benchmark_close > panel.benchmark_open
        cond_stock_down = panel.close < panel.open
        cond_benchmark_down = panel.benchmark_close < panel.benchmark_open

        # Row-wise broadcast against the benchmark conditions (no full
        # (dates × stocks) tiled copies).
        matches = cond_stock_up.where(cond_benchmark_up, False) | cond_stock_down.where(
            cond_benchmark_down, False
        )
        return matches.rolling(20).sum() / 20.0

    def alpha_183(self, panel: Alpha191Panel) -> pd.DataFrame:
        centered = panel.close - self.ts_mean(panel.close, 24)
        # cumsum(x)[-1] over a window is just the window sum
        sumac = centered.rolling(24).sum()
        return (self.ts_max(sumac, 24) - self.ts_min(sumac, 24)) / self.ts_stddev(
            panel.close, 24
        )

    def alpha_184(self, panel: Alpha191Panel) -> pd.DataFrame:
        rank1 = self.rank(
            self.corr(self.delay(panel.open - panel.close, 1), panel.close, 200)
        )
        rank2 = self.rank(panel.open - panel.close)
        return rank1 + rank2

    def alpha_185(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.rank(-((1 - (panel.open / panel.close)) ** 2))

    def alpha_186(self, panel: Alpha191Panel) -> pd.DataFrame:
        hd = panel.high - self.delay(panel.high, 1)
        ld = self.delay(panel.low, 1) - panel.low
        tr = np.maximum(
            np.maximum(
                panel.high - panel.low, (panel.high - self.delay(panel.close, 1)).abs()
            ),
            (panel.low - self.delay(panel.close, 1)).abs(),
        )
        sum_tr14 = self.ts_sum(tr, 14)
        sum1 = self.ts_sum(ld.where((ld > 0) & (ld > hd), 0.0), 14) * 100.0 / sum_tr14
        sum2 = self.ts_sum(hd.where((hd > 0) & (hd > ld), 0.0), 14) * 100.0 / sum_tr14
        mean1 = self.ts_mean(((sum1 - sum2).abs() / (sum1 + sum2) * 100.0), 6)
        return (mean1 + self.delay(mean1, 6)) / 2.0

    def alpha_187(self, panel: Alpha191Panel) -> pd.DataFrame:
        cond = panel.open <= self.delay(panel.open, 1)
        choice = np.maximum(
            panel.high - panel.open, panel.open - self.delay(panel.open, 1)
        )
        return choice.where(~cond, 0.0).rolling(20).sum()

    def alpha_188(self, panel: Alpha191Panel) -> pd.DataFrame:
        sma = self.sma(panel.high - panel.low, 11, 2)
        return ((panel.high - panel.low) - sma) / sma * 100.0

    def alpha_189(self, panel: Alpha191Panel) -> pd.DataFrame:
        return self.ts_mean((panel.close - self.ts_mean(panel.close, 6)).abs(), 6)

    def alpha_190(self, panel: Alpha191Panel) -> pd.DataFrame:
        ret1 = panel.close / self.delay(panel.close, 1) - 1.0
        benchmark = (panel.close / self.delay(panel.close, 19)) ** (1.0 / 20.0) - 1.0
        diff = ret1 - benchmark
        gt = ret1 > benchmark
        lt = ret1 < benchmark
        count_gt = gt.astype(float).rolling(20).sum()
        count_lt = lt.astype(float).rolling(20).sum()
        sum_lt = (diff.where(lt, 0.0) ** 2).rolling(20).sum()
        sum_gt = (diff.where(gt, 0.0) ** 2).rolling(20).sum()
        numerator = (count_gt - 1) * sum_lt
        denominator = count_lt * sum_gt
        return np.log(_safe_div(numerator, denominator))

    def alpha_191(self, panel: Alpha191Panel) -> pd.DataFrame:
        return (
            self.corr(self.ts_mean(panel.volume, 20), panel.low, 5)
            + (panel.high + panel.low) / 2.0
            - panel.close
        )
