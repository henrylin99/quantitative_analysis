"""港股量化分析共享数据层：宽表缓存（day × symbol 矩阵）。

数据源（data/ 目录，由港股行情页的同步链路生成，yfinance 日线）：
- hk_history.parquet  日线全池（symbol, day, open, high, low, close, volume）
- hk_snapshot.parquet 最新交易日截面（行情/形态旗标/估值/质量/风险/信号分）

宽表以 mtime 失效缓存，供市场结构/个股风险各类截面与时序计算复用，
口径与时间戳均为字符串日期（YYYY-MM-DD）。与美股侧 us_analytics_base
同构；港股暂无宏观/行业 ETF/季度财务辅助表，故不提供 aux_frame。
"""
from __future__ import annotations

import os

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "hk_history.parquet")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "hk_snapshot.parquet")

# ---------------------------------------------------------------- 宽表缓存

_CLOSE_WIDE: pd.DataFrame | None = None
_CLOSE_WIDE_MTIME: float | None = None
_DVOL_WIDE: pd.DataFrame | None = None
_DVOL_MTIME: float | None = None
_OHL_WIDE: dict[str, pd.DataFrame] | None = None
_OHL_MTIME: float | None = None


def _history_mtime() -> float:
    return os.path.getmtime(HISTORY_PATH)


def _normalize_day(h: pd.DataFrame) -> pd.DataFrame:
    h = h.copy()
    h["day"] = pd.to_datetime(h["day"]).dt.strftime("%Y-%m-%d")
    return h


def close_wide() -> pd.DataFrame:
    """day × symbol 收盘价矩阵（mtime 失效）。"""
    global _CLOSE_WIDE, _CLOSE_WIDE_MTIME
    mtime = _history_mtime()
    if _CLOSE_WIDE is not None and _CLOSE_WIDE_MTIME == mtime:
        return _CLOSE_WIDE
    h = pd.read_parquet(HISTORY_PATH, columns=["symbol", "day", "close"])
    _CLOSE_WIDE = (
        _normalize_day(h).pivot(index="day", columns="symbol", values="close")
        .sort_index().astype(float)
    )
    _CLOSE_WIDE_MTIME = mtime
    return _CLOSE_WIDE


def dvol_wide() -> pd.DataFrame:
    """day × symbol 港元成交额（volume × close）矩阵。"""
    global _DVOL_WIDE, _DVOL_MTIME
    mtime = _history_mtime()
    if _DVOL_WIDE is not None and _DVOL_MTIME == mtime:
        return _DVOL_WIDE
    h = pd.read_parquet(HISTORY_PATH, columns=["symbol", "day", "close", "volume"])
    h = _normalize_day(h)
    h["dvol"] = h["volume"].astype(float) * h["close"].astype(float)
    _DVOL_WIDE = (
        h.pivot(index="day", columns="symbol", values="dvol").sort_index().astype(float)
    )
    _DVOL_MTIME = mtime
    return _DVOL_WIDE


def ohl_wide() -> dict[str, pd.DataFrame]:
    """open/high/low/close 四张 day × symbol 矩阵（单次读取，mtime 失效）。"""
    global _OHL_WIDE, _OHL_MTIME
    mtime = _history_mtime()
    if _OHL_WIDE is not None and _OHL_MTIME == mtime:
        return _OHL_WIDE
    h = pd.read_parquet(
        HISTORY_PATH, columns=["symbol", "day", "open", "high", "low", "close"]
    )
    h = _normalize_day(h)
    out: dict[str, pd.DataFrame] = {}
    for col in ("open", "high", "low", "close"):
        out[col] = h.pivot(index="day", columns="symbol", values=col).sort_index().astype(float)
    _OHL_WIDE = out
    _OHL_MTIME = mtime
    return _OHL_WIDE


def history_tail(n_bars: int = 120) -> pd.DataFrame:
    """最近 n_bars 根日线的长表（用于技术旗标/OBV/Chaikin/VWAP 现算）。"""
    h = pd.read_parquet(
        HISTORY_PATH,
        columns=["symbol", "day", "open", "high", "low", "close", "volume"],
    )
    h = _normalize_day(h).sort_values(["symbol", "day"])
    return h.groupby("symbol", group_keys=False).tail(n_bars)


def snapshot_frame() -> pd.DataFrame:
    return pd.read_parquet(SNAPSHOT_PATH)


def symbols() -> list[str]:
    return sorted(close_wide().columns.tolist())
