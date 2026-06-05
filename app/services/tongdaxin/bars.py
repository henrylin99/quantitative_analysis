from __future__ import annotations

import pandas as pd

from app.services.tongdaxin.code_mapping import tdx_market_code_to_bs_style


TDX_CATEGORY_MAP = {
    "5min": 0,
    "15min": 1,
    "30min": 2,
    "60min": 3,
}


def period_type_to_tdx_category(period_type: str) -> int:
    if period_type not in TDX_CATEGORY_MAP:
        raise ValueError(f"unsupported tongdaxin period_type: {period_type}")
    return TDX_CATEGORY_MAP[period_type]


def normalize_tdx_minute_bars(payload, market: int, code: str, period_type: str) -> pd.DataFrame:
    period_type_to_tdx_category(period_type)
    df = pd.DataFrame(list(payload or []))
    if df.empty:
        return pd.DataFrame(
            columns=[
                "ts_code",
                "datetime",
                "period_type",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "pre_close",
                "change",
                "pct_chg",
            ]
        )

    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    for column in ["open", "high", "low", "close", "vol", "amount"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["ts_code"] = tdx_market_code_to_bs_style(market, code)
    df["period_type"] = period_type
    df["volume"] = df["vol"]
    df["pre_close"] = df["close"].shift(1)
    if not df.empty:
        df.loc[df.index[0], "pre_close"] = df.loc[df.index[0], "close"]
    df["change"] = df["close"] - df["pre_close"]
    df["pct_chg"] = ((df["change"] / df["pre_close"]) * 100).fillna(0).round(4)
    if not df.empty:
        df.loc[df.index[0], ["change", "pct_chg"]] = [0, 0]
    return df[
        [
            "ts_code",
            "datetime",
            "period_type",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pre_close",
            "change",
            "pct_chg",
        ]
    ]
