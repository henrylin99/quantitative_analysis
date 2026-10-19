from __future__ import annotations

import pandas as pd

FLAG_WEIGHTS: dict[str, float] = {
    # Bullish signals
    "pattern_ma_bull":             15.0,
    "pattern_trend_confirm":       12.0,
    "break_high_60":               10.0,
    "break_high_20":                8.0,
    "consec_up_5":                  8.0,
    "pattern_platform_breakout":    8.0,
    "pattern_volume_breakout":      7.0,
    "pattern_pullback_hold":        7.0,
    "pattern_three_white_soldiers": 6.0,
    "pattern_bullish_engulfing":    5.0,
    "pattern_double_bottom":        5.0,
    "pattern_hammer":               4.0,
    "consec_up_3":                  3.0,
    "pattern_bull_candle":          3.0,
    # Bearish penalties
    "pattern_false_breakout":      -8.0,
    "pattern_three_black_crows":   -6.0,
    "pattern_long_upper_shadow":   -4.0,
    "pattern_bear_candle":         -3.0,
    "pattern_shooting_star":       -3.0,
}

_CONTINUOUS_BONUS_COLS = ["ret_20d", "roe", "profit_margin", "revenue_growth"]
_BONUS_PER_COL = 5.0  # max bonus points per continuous metric


def _percentile_rank(series: pd.Series) -> pd.Series:
    """0–1 percentile rank across non-NaN values; NaN rows get NaN."""
    return series.rank(pct=True, na_option="keep")


def compute_scores(snapshot: pd.DataFrame) -> pd.Series:
    """
    Composite signal score (0–100) for each row.

    Components:
      - Flag score: weighted sum of binary flag columns present in snapshot
      - Continuous bonus: percentile-ranked ret_20d/roe/profit_margin/revenue_growth (≤5 pts each)
      - PE penalty: -5 if forward_pe > 50; additional -5 if forward_pe > 100
    """
    score = pd.Series(0.0, index=snapshot.index)

    for col, weight in FLAG_WEIGHTS.items():
        if col in snapshot.columns:
            score += snapshot[col].fillna(0).astype(float) * weight

    for col in _CONTINUOUS_BONUS_COLS:
        if col in snapshot.columns:
            score += _percentile_rank(snapshot[col]).fillna(0) * _BONUS_PER_COL

    if "forward_pe" in snapshot.columns:
        pe = pd.to_numeric(snapshot["forward_pe"], errors="coerce")
        score -= (pe > 50).fillna(False).astype(float) * 5.0
        score -= (pe > 100).fillna(False).astype(float) * 5.0

    return score.clip(0, 100).round(1)
