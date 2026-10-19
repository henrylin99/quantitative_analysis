from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


REQUIRED_NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume"]
OPTIONAL_NUMERIC_COLUMNS = ["amount"]
CONTINUOUS_COLUMNS = [
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_ratio_5",
    "amplitude",
    "body_ratio",
    "upper_shadow_ratio",
    "lower_shadow_ratio",
    # 财务指标
    "forward_pe",
    "trailing_pe",
    "price_to_book",
    "revenue_growth",
    "earnings_growth",
    "roe",
    "profit_margin",
    # 风险指标
    "risk_ma20_dev",
    "risk_ma60_dev",
    "risk_dd_20d",
    "risk_vol_20d",
]
FLAG_COLUMNS = [
    "pattern_bull_candle",
    "pattern_bear_candle",
    "pattern_hammer",
    "pattern_shooting_star",
    "pattern_doji",
    "pattern_long_upper_shadow",
    "pattern_long_lower_shadow",
    "pattern_bullish_engulfing",
    "pattern_bearish_engulfing",
    "pattern_inside_bar",
    "pattern_three_white_soldiers",
    "pattern_three_black_crows",
    "pattern_ma_bull",
    "pattern_trend_confirm",
    "pattern_pullback_hold",
    "pattern_double_bottom",
    "pattern_platform_breakout",
    "pattern_false_breakout",
    "pattern_volume_breakout",
    "pattern_volume_shrink_pullback",
    "pattern_volatility_contraction",
    "pattern_volatility_expansion",
    "break_high_20",
    "break_high_60",
    "consec_up_3",
    "consec_up_5",
]

FINANCIAL_COLUMNS = [
    # 估值指标
    "market_cap",
    "forward_pe",
    "trailing_pe",
    "price_to_book",
    "peg_ratio",
    "ps_ratio",
    # 成长指标
    "revenue_growth",
    "earnings_growth",
    # 盈利能力
    "roe",
    "roa",
    "profit_margin",
    "operating_margin",
    # 财务健康
    "debt_to_equity",
    "current_ratio",
    # 股息
    "dividend_yield",
    "dividend_rate",
]


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["day"] = pd.to_datetime(result["day"])
    result = result.sort_values("day").reset_index(drop=True)

    for column in REQUIRED_NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    for column in OPTIONAL_NUMERIC_COLUMNS:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")

    price_range = result["high"] - result["low"]
    body = (result["close"] - result["open"]).abs()
    upper_shadow = result["high"] - result[["open", "close"]].max(axis=1)
    lower_shadow = result[["open", "close"]].min(axis=1) - result["low"]
    pre_close = result["close"].shift(1)
    prior_high_20 = result["high"].shift(1).rolling(20, min_periods=20).max()
    prior_high_60 = result["high"].shift(1).rolling(60, min_periods=60).max()
    prior_low_20 = result["low"].shift(1).rolling(20, min_periods=20).min()
    rolling_amp_5 = _safe_divide(
        result["high"].rolling(5, min_periods=5).max() - result["low"].rolling(5, min_periods=5).min(),
        result["close"].rolling(5, min_periods=5).mean(),
    )
    rolling_amp_20 = _safe_divide(
        result["high"].rolling(20, min_periods=20).max() - result["low"].rolling(20, min_periods=20).min(),
        result["close"].rolling(20, min_periods=20).mean(),
    )
    volume_ma_5 = result["volume"].rolling(5, min_periods=5).mean()
    up_days = result["close"].diff().gt(0).astype(int)

    result["pre_close"] = pre_close
    result["change"] = result["close"] - pre_close
    result["pct_change"] = _safe_divide(result["change"], pre_close)

    for window in (5, 10, 20, 60):
        result[f"ma{window}"] = result["close"].rolling(window, min_periods=window).mean()

    result["ret_1d"] = _safe_divide(result["close"], pre_close) - 1
    result["ret_5d"] = _safe_divide(result["close"], result["close"].shift(5)) - 1
    result["ret_20d"] = _safe_divide(result["close"], result["close"].shift(20)) - 1
    result["vol_ratio_5"] = _safe_divide(result["volume"], volume_ma_5)
    result["amplitude"] = _safe_divide(result["high"] - result["low"], pre_close)
    result["body_ratio"] = _safe_divide(body, price_range)
    result["upper_shadow_ratio"] = _safe_divide(upper_shadow, price_range)
    result["lower_shadow_ratio"] = _safe_divide(lower_shadow, price_range)

    result["pattern_bull_candle"] = (result["close"] > result["open"]).astype(int)
    result["pattern_bear_candle"] = (result["close"] < result["open"]).astype(int)
    result["pattern_hammer"] = (
        (result["lower_shadow_ratio"] >= 0.55)
        & (result["body_ratio"] <= 0.30)
        & (result["upper_shadow_ratio"] <= 0.20)
    )
    result["pattern_shooting_star"] = (
        (result["upper_shadow_ratio"] >= 0.55)
        & (result["body_ratio"] <= 0.30)
        & (result["lower_shadow_ratio"] <= 0.20)
    )
    result["pattern_doji"] = (result["body_ratio"] <= 0.10)
    result["pattern_long_upper_shadow"] = (result["upper_shadow_ratio"] >= 0.45)
    result["pattern_long_lower_shadow"] = (result["lower_shadow_ratio"] >= 0.45)

    prev_open = result["open"].shift(1)
    prev_close = result["close"].shift(1)
    prev_high = result["high"].shift(1)
    prev_low = result["low"].shift(1)
    prev_body = (prev_close - prev_open).abs()
    prev_open_buffer = prev_body * 0.5

    result["pattern_bullish_engulfing"] = (
        (prev_close < prev_open)
        & (result["close"] > result["open"])
        & (result["open"] <= prev_close)
        & (result["close"] >= prev_open)
        & (body >= prev_body)
    )
    result["pattern_bearish_engulfing"] = (
        (prev_close > prev_open)
        & (result["close"] < result["open"])
        & (result["open"] >= prev_close)
        & (result["close"] <= prev_open)
        & (body >= prev_body)
    )
    result["pattern_inside_bar"] = (result["high"] <= prev_high) & (result["low"] >= prev_low)

    prev2_close = result["close"].shift(2)
    prev2_open = result["open"].shift(2)
    result["pattern_three_white_soldiers"] = (
        result["pattern_bull_candle"].eq(1)
        & result["pattern_bull_candle"].shift(1).eq(1)
        & result["pattern_bull_candle"].shift(2).eq(1)
        & result["close"].gt(prev_close)
        & prev_close.gt(prev2_close)
        & result["open"].ge(prev_open)
        & result["open"].le(prev_close + prev_open_buffer)
        & prev_open.ge(prev2_open)
        & prev_open.le(prev2_close + prev_body.shift(1) * 0.5)
    )
    result["pattern_three_black_crows"] = (
        result["pattern_bear_candle"].eq(1)
        & result["pattern_bear_candle"].shift(1).eq(1)
        & result["pattern_bear_candle"].shift(2).eq(1)
        & result["close"].lt(prev_close)
        & prev_close.lt(prev2_close)
        & result["open"].le(prev_open)
        & result["open"].ge(prev_close - prev_open_buffer)
        & prev_open.le(prev2_open)
        & prev_open.ge(prev2_close - prev_body.shift(1) * 0.5)
    )

    ma_alignment = (
        result["close"].gt(result["ma20"])
        & result["ma20"].gt(result["ma60"])
        & result["ma60"].notna()
    )
    result["pattern_ma_bull"] = ma_alignment
    result["break_high_20"] = result["close"].gt(prior_high_20)
    result["break_high_60"] = result["close"].gt(prior_high_60)
    result["pattern_trend_confirm"] = (
        result["pattern_ma_bull"].eq(1)
        & result["ret_20d"].gt(0)
        & result["break_high_20"].eq(1)
    )
    result["pattern_pullback_hold"] = (
        result["ma20"].notna()
        & result["close"].gt(result["ma20"])
        & result["low"].le(result["ma20"] * 1.02)
        & result["ret_1d"].gt(0)
    )
    result["pattern_double_bottom"] = _detect_double_bottom(result["low"], result["close"])
    result["pattern_platform_breakout"] = (
        result["close"].gt(prior_high_20)
        & _safe_divide(prior_high_20 - prior_low_20, result["close"].shift(1)).le(0.08)
    )
    result["pattern_false_breakout"] = (
        result["high"].gt(prior_high_20)
        & result["close"].lt(prior_high_20)
    )

    result["pattern_volume_breakout"] = (
        result["close"].gt(prev_high)
        & result["volume"].gt(volume_ma_5 * 1.5)
    )
    result["pattern_volume_shrink_pullback"] = (
        result["ma20"].notna()
        & result["close"].gt(result["ma20"])
        & result["ret_1d"].lt(0)
        & result["volume"].lt(volume_ma_5 * 0.8)
    )
    result["pattern_volatility_contraction"] = (
        rolling_amp_5.notna()
        & rolling_amp_20.notna()
        & rolling_amp_5.lt(rolling_amp_20 * 0.8)
        & result["amplitude"].lt(rolling_amp_20)
    )
    result["pattern_volatility_expansion"] = (
        result["amplitude"].gt(result["amplitude"].shift(1).rolling(5, min_periods=5).mean() * 1.2)
    )

    result["consec_up_3"] = up_days.rolling(3, min_periods=3).sum().eq(3)
    result["consec_up_5"] = up_days.rolling(5, min_periods=5).sum().eq(5)

    # Risk metrics (continuous, % units)
    result["risk_ma20_dev"] = _safe_divide(result["close"] - result["ma20"], result["ma20"]) * 100
    result["risk_ma60_dev"] = _safe_divide(result["close"] - result["ma60"], result["ma60"]) * 100

    rolling_peak_20 = result["close"].rolling(20, min_periods=5).max()
    result["risk_dd_20d"] = _safe_divide(result["close"] - rolling_peak_20, rolling_peak_20) * 100

    result["risk_vol_20d"] = result["ret_1d"].rolling(20, min_periods=10).std() * 100

    for column in FLAG_COLUMNS:
        result[column] = result[column].fillna(False).astype(int)

    result["day"] = result["day"].dt.strftime("%Y-%m-%d")
    return result


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(denominator.abs() > 1e-12, numerator / denominator, np.nan),
        index=numerator.index,
        dtype="float64",
    )


def _detect_double_bottom(low: pd.Series, close: pd.Series) -> pd.Series:
    values = []
    for index in range(len(low)):
        if index < 9:
            values.append(False)
            continue

        window_low = low.iloc[max(0, index - 19): index + 1]
        window_close = close.iloc[max(0, index - 19): index + 1]
        troughs = window_low.nsmallest(2)
        if len(troughs) < 2:
            values.append(False)
            continue

        first_idx, second_idx = sorted(troughs.index[:2])
        if second_idx - first_idx < 3:
            values.append(False)
            continue

        trough_gap = abs(window_low.loc[first_idx] - window_low.loc[second_idx])
        trough_level = max(abs(window_low.loc[first_idx]), abs(window_low.loc[second_idx]), 1e-12)
        neckline = window_close.loc[first_idx:second_idx].max()
        values.append(trough_gap / trough_level <= 0.03 and close.iloc[index] > neckline)

    return pd.Series(values, index=low.index, dtype="bool")


def add_financial_features(
    df: pd.DataFrame,
    financial_metrics: dict[str, Any],
) -> pd.DataFrame:
    """
    将财务指标添加到最新一行数据

    Args:
        df: 经过 add_features 处理的历史数据 DataFrame
        financial_metrics: 从 yfinance 获取的财务指标字典

    Returns:
        添加了财务列的 DataFrame
    """
    result = df.copy()

    # 创建财务指标列，初始值都为 pd.NA
    for col in FINANCIAL_COLUMNS:
        result[col] = pd.NA

    # 只在最新一行添加财务数据
    if not result.empty and financial_metrics:
        latest_idx = result.index[-1]

        result.loc[latest_idx, "market_cap"] = financial_metrics.get("market_cap")
        result.loc[latest_idx, "forward_pe"] = financial_metrics.get("forward_pe")
        result.loc[latest_idx, "trailing_pe"] = financial_metrics.get("trailing_pe")
        result.loc[latest_idx, "price_to_book"] = financial_metrics.get("price_to_book")
        result.loc[latest_idx, "peg_ratio"] = financial_metrics.get("peg_ratio")
        result.loc[latest_idx, "ps_ratio"] = financial_metrics.get("ps_ratio")
        result.loc[latest_idx, "revenue_growth"] = financial_metrics.get("revenue_growth")
        result.loc[latest_idx, "earnings_growth"] = financial_metrics.get("earnings_growth")
        result.loc[latest_idx, "roe"] = financial_metrics.get("roe")
        result.loc[latest_idx, "roa"] = financial_metrics.get("roa")
        result.loc[latest_idx, "profit_margin"] = financial_metrics.get("profit_margin")
        result.loc[latest_idx, "operating_margin"] = financial_metrics.get("operating_margin")
        result.loc[latest_idx, "debt_to_equity"] = financial_metrics.get("debt_to_equity")
        result.loc[latest_idx, "current_ratio"] = financial_metrics.get("current_ratio")
        result.loc[latest_idx, "dividend_yield"] = financial_metrics.get("dividend_yield")
        result.loc[latest_idx, "dividend_rate"] = financial_metrics.get("dividend_rate")

    return result
