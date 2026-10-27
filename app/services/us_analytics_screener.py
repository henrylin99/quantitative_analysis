"""美股扫描器服务层：单日截面全字段行集（快照字段 + 现算技术指标/旗标）。

数据一律经 ``app/services/us_analytics_base.py``：
- snapshot_frame()   最新交易日截面（行情/形态/估值/风险/信号分等全字段）
- history_tail(120)  最近 120 根日线长表（用于现算振荡器/趋势/量能指标）

快照没有、但前端扫描器需要的列在此现算：RSI/MACD/ADX/DI/CCI/Stoch/WillR/MFI/
布林带/ATR/OBV/Chaikin/VWAP，以及 23 个 ind_* 二元旗标（阈值取通用技术分析
惯例：ADX>25、CCI±100、Stoch 20/80、RSI 30/70、WillR −80/−20、MFI 20/80、
布林触带与低分位收口、OBV 高于其 EMA20、Chaikin OSC>0、收盘高于 VWAP；
cross 类旗标 = 最后一根 K 线发生的上穿/下穿；RSI 底背离为近似判定——
收盘价创近 20 日新低而 RSI 高于前低点当日）。

注意：日线历史无成交额列，VWAP 用近 20 根「典型价 (H+L+C)/3 × 成交量」
加权近似（口径在 docstring 与字段注释中声明）。所有指标仅用最近 120 根
计算，Wilder 类递推为截尾近似。

base() 结果按（快照 mtime, 行情 mtime）模块级缓存；numpy/nan 清洗为原生
类型/None。返回 {"rows": [...]}。
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .us_analytics_base import history_tail, snapshot_frame

TAIL_BARS = 120  # 指标现算回看根数

# ---------------------------------------------------------------- 类型清洗


def _clean(v: Any) -> Any:
    """递归清洗为 JSON 安全的原生类型：NaN/inf → None，numpy 标量 → python 标量。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return v
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (list, tuple, np.ndarray, pd.Series)):
        return [_clean(x) for x in (v.tolist() if hasattr(v, "tolist") else v)]
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if hasattr(v, "item"):
        try:
            return _clean(v.item())
        except Exception:  # noqa: BLE001
            return str(v)
    return v


# ---------------------------------------------------------------- 指标原子

def _ema(s: pd.Series, span: int) -> pd.Series:
    """标准 EMA（adjust=False，等价递推 y_t = α·x_t + (1−α)·y_{t−1}）。"""
    return s.ewm(span=span, adjust=False).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder 平滑（α=1/n），RSI/ATR/ADX 的标准递推。"""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI。平均损失为 0 时置 100。"""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = _wilder(gain, n)
    al = _wilder(loss, n)
    rs = ag / al.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(al != 0, 100.0).where(ag.notna())


def _atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    """Wilder ATR：真波幅（含跳空）的 α=1/n 平滑。"""
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return _wilder(tr, n)


def _adx_di(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14):
    """Wilder ADX 与 +DI/−DI。返回 (adx, plus_di, minus_di)。"""
    up = h.diff()
    down = -l.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=h.index)
    atr = _atr(h, l, c, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * _wilder(plus_dm, n) / atr
        minus_di = 100.0 * _wilder(minus_dm, n) / atr
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return _wilder(dx.replace(np.nan, 0.0), n), plus_di, minus_di


def _cci(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 20) -> pd.Series:
    """CCI：典型价对 n 期 SMA 的偏离，除以 0.015×平均绝对偏差。"""
    tp = (h + l + c) / 3.0
    sma = tp.rolling(n).mean()
    md = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (tp - sma) / (0.015 * md)


def _stoch(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14):
    """随机指标：返回 (%K, %D=K 的 3 期 SMA)。"""
    llv = l.rolling(n).min()
    hhv = h.rolling(n).max()
    rng = hhv - llv
    k = 100.0 * (c - llv) / rng.where(rng != 0)
    return k, k.rolling(3).mean()


def _willr(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    """威廉指标 %R：−100×(HHV−C)/(HHV−LLV)。"""
    llv = l.rolling(n).min()
    hhv = h.rolling(n).max()
    rng = hhv - llv
    return -100.0 * (hhv - c) / rng.where(rng != 0)


def _mfi(h: pd.Series, l: pd.Series, c: pd.Series, v: pd.Series, n: int = 14) -> pd.Series:
    """资金流量指数 MFI：典型价×量的正/负资金流 14 期比值。"""
    tp = (h + l + c) / 3.0
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0.0).rolling(n).sum()
    neg = mf.where(tp < tp.shift(1), 0.0).rolling(n).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = pos / neg.replace(0.0, np.nan)
        out = 100.0 - 100.0 / (1.0 + ratio)
    return out.where(neg != 0, 100.0).where(pos.notna())


def _macd_hist(c: pd.Series) -> pd.Series:
    """MACD 柱：DIF(EMA12−EMA26) − DEA(9 期 EMA of DIF)。"""
    dif = _ema(c, 12) - _ema(c, 26)
    return dif - _ema(dif, 9)


def _bbands(c: pd.Series, n: int = 20, k: float = 2.0):
    """布林带（n 期 SMA ± k×总体标准差 ddof=0）。返回 (upper, mid, lower)。"""
    mid = c.rolling(n).mean()
    sd = c.rolling(n).std(ddof=0)
    return mid + k * sd, mid, mid - k * sd


def _obv(c: pd.Series, v: pd.Series) -> pd.Series:
    """能量潮 OBV：收盘涨跌符号 × 成交量的累计和。"""
    return (np.sign(c.diff()).fillna(0.0) * v).cumsum()


def _chaikin_osc(h: pd.Series, l: pd.Series, c: pd.Series, v: pd.Series) -> pd.Series:
    """Chaikin 振荡器：A/D 线的 EMA3 − EMA10。A/D 乘数 = ((C−L)−(H−C))/(H−L)。"""
    rng = (h - l).replace(0.0, np.nan)
    mfm = ((c - l) - (h - c)) / rng
    adl = (mfm.fillna(0.0) * v).cumsum()
    return _ema(adl, 3) - _ema(adl, 10)


def _vwap20(h: pd.Series, l: pd.Series, c: pd.Series, v: pd.Series) -> float:
    """近 20 根 VWAP。历史无成交额列，用典型价×量近似（金额加权口径的替代）。"""
    tp = (h + l + c) / 3.0
    w = tp.tail(20) * v.tail(20)
    tot = float(v.tail(20).sum())
    return float(w.sum() / tot) if tot else float("nan")


# ---------------------------------------------------------------- 旗标

def _crossed_up(a: pd.Series, b: pd.Series) -> bool:
    """最后一根 K 线 a 上穿 b：前一根 a≤b 且当前 a>b。"""
    if len(a) < 2:
        return False
    a0, a1 = a.iloc[-2], a.iloc[-1]
    b0, b1 = b.iloc[-2], b.iloc[-1]
    for x in (a0, a1, b0, b1):
        if pd.isna(x):
            return False
    return a0 <= b0 and a1 > b1


def _crossed_down(a: pd.Series, b: pd.Series) -> bool:
    """最后一根 K 线 a 下穿 b：前一根 a≥b 且当前 a<b。"""
    if len(a) < 2:
        return False
    a0, a1 = a.iloc[-2], a.iloc[-1]
    b0, b1 = b.iloc[-2], b.iloc[-1]
    for x in (a0, a1, b0, b1):
        if pd.isna(x):
            return False
    return a0 >= b0 and a1 < b1


def _rsi_bull_divergence(close: pd.Series, rsi: pd.Series, look: int = 20) -> bool:
    """RSI 底背离（近似判定）：今日收盘创近 20 日新低，且 RSI 高于
    前一个低点当日的 RSI（价新低而 RSI 抬高）。"""
    if len(close) < look + 1:
        return False
    c = close.iloc[-1]
    prev = close.iloc[-(look + 1):-1]
    if pd.isna(c):
        return False
    if c > prev.min():
        return False
    idx = prev.idxmin()
    r_prev = rsi.get(idx)
    r_now = rsi.iloc[-1]
    if r_prev is None or pd.isna(r_prev) or pd.isna(r_now):
        return False
    return bool(r_now > r_prev)


# ---------------------------------------------------------------- 单票指标行

def _indicator_row(sub: pd.DataFrame) -> dict[str, Any]:
    """单票最近 TAIL_BARS 根日线 → 现算指标值 + 23 个 ind_* 旗标。

    返回的 dict 键即 base() 行中快照之外的全部新增列。
    """
    sub = sub.sort_values("day").tail(TAIL_BARS).reset_index(drop=True)
    out: dict[str, Any] = {}
    if len(sub) < 5:
        return out
    h, l, c, v = sub["high"], sub["low"], sub["close"], sub["volume"].astype(float)

    rsi = _rsi(c)
    macd = _macd_hist(c)
    dif = _ema(c, 12) - _ema(c, 26)
    dea = _ema(dif, 9)
    adx, pdi, mdi = _adx_di(h, l, c)
    cci = _cci(h, l, c)
    k, d = _stoch(h, l, c)
    wr = _willr(h, l, c)
    mfi = _mfi(h, l, c, v)
    bb_u, bb_m, bb_l = _bbands(c)
    width = (bb_u - bb_l) / bb_m.where(bb_m != 0)
    atr = _atr(h, l, c)
    obv = _obv(c, v)
    chg_osc = _chaikin_osc(h, l, c, v)
    vwap = _vwap20(h, l, c, v)

    def last(s: pd.Series) -> Any:
        x = s.iloc[-1]
        return _clean(float(x)) if pd.notna(x) else None

    close_last = float(c.iloc[-1])
    out.update({
        "rsi_14": last(rsi), "macd_hist": last(macd),
        "adx_14": last(adx), "cci_20": last(cci),
        "stoch_k_14": last(k), "willr_14": last(wr), "mfi_14": last(mfi),
        "bb_upper": last(bb_u), "bb_mid": last(bb_m), "bb_lower": last(bb_l),
        "bb_width": last(width), "atr_14": last(atr),
        "atr_stop_long": _clean(close_last - 2.0 * float(atr.iloc[-1]))
        if pd.notna(atr.iloc[-1]) else None,
        "di_plus_14": last(pdi), "di_minus_14": last(mdi),
        "vwap": _clean(vwap), "obv": last(obv), "chaikin_osc": last(chg_osc),
    })

    # 二元旗标：1/0，输入缺失时 0（旗标语义为「未触发」）
    def flag(x: Any) -> int:
        return int(x == x and bool(x)) if x is not None else 0

    def num(s: pd.Series) -> float:
        x = s.iloc[-1]
        return float(x) if pd.notna(x) else float("nan")

    width_q = width.dropna().quantile(0.2) if width.notna().sum() >= 10 else np.nan
    width_now = width.iloc[-1] if len(width) else np.nan

    out.update({
        "ind_adx_strong_trend": flag(num(adx) > 25),
        "ind_di_bull_cross": int(_crossed_up(pdi, mdi)),
        "ind_cci_oversold": flag(num(cci) < -100),
        "ind_cci_overbought": flag(num(cci) > 100),
        "ind_stoch_oversold": flag(num(k) < 20),
        "ind_stoch_overbought": flag(num(k) > 80),
        "ind_stoch_bull_cross": int(_crossed_up(k, d)),
        "ind_macd_bull_cross": int(_crossed_up(dif, dea)),
        "ind_macd_bear_cross": int(_crossed_down(dif, dea)),
        "ind_macd_hist_positive": flag(num(macd) > 0),
        "ind_rsi_oversold": flag(num(rsi) < 30),
        "ind_rsi_overbought": flag(num(rsi) > 70),
        "ind_rsi_bull_divergence": int(_rsi_bull_divergence(c, rsi)),
        "ind_willr_oversold": flag(num(wr) < -80),
        "ind_willr_overbought": flag(num(wr) > -20),
        "ind_mfi_oversold": flag(num(mfi) < 20),
        "ind_mfi_overbought": flag(num(mfi) > 80),
        "ind_bb_squeeze": int(pd.notna(width_now) and pd.notna(width_q)
                              and width_now <= width_q),
        "ind_bb_upper_touch": flag(float(h.iloc[-1]) >= float(bb_u.iloc[-1]))
        if pd.notna(bb_u.iloc[-1]) else 0,
        "ind_bb_lower_touch": flag(float(l.iloc[-1]) <= float(bb_l.iloc[-1]))
        if pd.notna(bb_l.iloc[-1]) else 0,
        "ind_obv_uptrend": flag(num(obv) > num(_ema(obv, 20))),
        "ind_chaikin_bullish": flag(num(chg_osc) > 0),
        "ind_price_above_vwap": flag(close_last > vwap) if pd.notna(vwap) else 0,
    })

    # 方向计票：与前端信号面板同口径——看涨旗标计数 / 看跌旗标计数
    bull_keys = (
        "ind_adx_strong_trend", "ind_di_bull_cross",
        "ind_cci_oversold", "ind_stoch_oversold", "ind_stoch_bull_cross",
        "ind_macd_bull_cross", "ind_macd_hist_positive",
        "ind_rsi_oversold", "ind_rsi_bull_divergence",
        "ind_willr_oversold", "ind_mfi_oversold",
        "ind_bb_lower_touch", "ind_obv_uptrend", "ind_chaikin_bullish",
        "ind_price_above_vwap",
    )
    bear_keys = (
        "ind_cci_overbought", "ind_stoch_overbought", "ind_macd_bear_cross",
        "ind_rsi_overbought", "ind_willr_overbought", "ind_mfi_overbought",
        "ind_bb_upper_touch",
    )
    out["ta_with_trend"] = sum(int(out[k]) for k in bull_keys)
    out["ta_counter_trend"] = sum(int(out[k]) for k in bear_keys)
    return out


# ---------------------------------------------------------------- base()

_BASE_CACHE: dict[tuple, Any] = {"key": None, "data": None}

_IND_VALUE_COLS = (
    "rsi_14", "macd_hist", "adx_14", "cci_20", "stoch_k_14", "willr_14",
    "mfi_14", "bb_upper", "bb_mid", "bb_lower", "bb_width", "atr_14",
    "atr_stop_long", "di_plus_14", "di_minus_14", "vwap", "obv", "chaikin_osc",
)


def _cache_key() -> tuple:
    """缓存键：快照文件与行情文件的 mtime 组合。"""
    import os

    from .us_analytics_base import HISTORY_PATH, SNAPSHOT_PATH
    parts = []
    for p in (SNAPSHOT_PATH, HISTORY_PATH):
        try:
            parts.append(os.path.getmtime(p))
        except OSError:
            parts.append(0.0)
    return tuple(parts)


def base() -> dict:
    """单日截面全字段行集：快照全字段 + 现算技术指标/旗标，逐票一行。

    合并两个来源：(a) snapshot_frame() 的最新截面（行情/形态旗标/动量/估值/
    风险/信号分等）；(b) 由最近 120 根日线现算的振荡器/趋势/量能指标值与
    23 个 ind_* 旗标、方向计票 ta_with_trend / ta_counter_trend。
    返回 {"rows": [...]}，行序按 symbol 升序；所有值经 _clean 清洗。
    """
    ck = _cache_key()
    if _BASE_CACHE["key"] == ck and _BASE_CACHE["data"] is not None:
        return _BASE_CACHE["data"]

    snap = snapshot_frame()
    tail = history_tail(TAIL_BARS)
    by_sym: dict[str, dict[str, Any]] = {}
    for sym, sub in tail.groupby("symbol"):
        row = _indicator_row(sub)
        if row:
            by_sym[sym] = row

    snap = snap.sort_values("symbol")
    rows: list[dict] = []
    for rec in snap.to_dict(orient="records"):
        sym = rec.get("symbol")
        row = {k: _clean(v) for k, v in rec.items()}
        ind = by_sym.get(sym, {})
        row.update(ind)
        rows.append(row)

    out = {"rows": rows}
    _BASE_CACHE["key"] = ck
    _BASE_CACHE["data"] = out
    return out
