"""港股市场级分析服务：市场内部结构（宽度）、相对强度、波动率 regime、
波动率期限结构（cone）、截面离散度、收益持续性、日历季节性、隔夜/日内分解。

共 8 个函数，全部基于共享数据层 hk_analytics_base 的 day × symbol 宽表计算：
internals / relstrength / volregime / volcone / dispersion / persistence /
seasonality / overnight。返回 dict 的键结构与开源参考实现的对应端点一致
（键名、嵌套、单位均对齐，series 的 time 字段为 Unix 秒），可直接被前端
按同样页面结构渲染。所有输出经 _clean 递归转换为 JSON 原生类型
（nan/inf → None，numpy 数组 → list，numpy 标量 → float/int）。

口径约定（与参考实现一致）：
- 市场聚合 = 全池等权（逐日截面均值），非市值加权；
- 实现波动率 = 简单收益 rolling std(ddof=1) × sqrt(252)；
- 日期统一为 'YYYY-MM-DD' 字符串（宽表索引即此格式），序列点 time 为 epoch 秒。
"""
from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
import pandas as pd

from . import hk_analytics_base as base

# --------------------------------------------------------------------------- #
# 工具：JSON 安全化 + 名称映射 + 时间戳
# --------------------------------------------------------------------------- #


def _clean(obj: Any) -> Any:
    """递归 JSON 安全化：nan/inf → None，np 数组 → list，np 标量 → float/int。"""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_clean(v) for v in obj.tolist()]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, np.bool_)):
        obj = obj.item()
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def _names() -> dict[str, str]:
    """symbol → 公司名映射（来自最新截面快照）。"""
    try:
        df = base.snapshot_frame()
        if "symbol" in df.columns and "name" in df.columns:
            return dict(zip(df["symbol"].astype(str), df["name"].astype(str)))
    except Exception:
        pass
    return {}


def _ts(d) -> int:
    """日期（'YYYY-MM-DD' 字符串或 Timestamp）→ Unix 秒。"""
    return int(pd.Timestamp(d).value // 10**9)


def _series_of(s: pd.Series) -> list[dict]:
    """Series → [{time: epoch 秒, value: float}]，跳过 nan。"""
    return [{"time": _ts(d), "value": _clean(float(v))}
            for d, v in s.items() if v == v]


def _history_mtime() -> float:
    return os.path.getmtime(base.HISTORY_PATH)


# --------------------------------------------------------------------------- #
# 市场内部结构（宽度 / A/D 线 / McClellan / %above-MA / 新高新低）
# --------------------------------------------------------------------------- #

_INTERNALS_CACHE: tuple[float, dict] | None = None


def internals(ma_short: int = 50, ma_long: int = 200, new_high: int = 20) -> dict:
    """全历史市场内部结构：逐日涨跌家数、A/D 线、McClellan 振荡器、
    %above-MA{50,200}、new_high 档新高/新低计数与 Zweig 宽度推力事件；
    series 按日升序，latest 为最新一日摘要；结果按历史文件 mtime 缓存。"""
    global _INTERNALS_CACHE
    params = (int(ma_short), int(ma_long), int(new_high))
    mtime = _history_mtime()
    if _INTERNALS_CACHE is not None and _INTERNALS_CACHE[0] == mtime \
            and _INTERNALS_CACHE[1].get("ma_short") == params[0] \
            and _INTERNALS_CACHE[1].get("ma_long") == params[1] \
            and _INTERNALS_CACHE[1].get("new_high") == params[2]:
        return _INTERNALS_CACHE[1]

    ma_short, ma_long, new_high = params
    empty = {"ma_short": ma_short, "ma_long": ma_long, "new_high": new_high,
             "n_days": 0, "series": [], "latest": None,
             "thrusts": [], "params": {"thrust_low": 0.40, "thrust_high": 0.615}}
    close = base.close_wide()
    if close.empty:
        return empty
    ma_short = max(2, ma_short)
    ma_long = max(ma_short + 1, ma_long)
    new_high = max(2, new_high)

    ret = close.pct_change()
    adv = (ret > 0).sum(axis=1)
    dec = (ret < 0).sum(axis=1)
    unc = (ret == 0).sum(axis=1)
    total = ret.notna().sum(axis=1)
    net = adv - dec

    ad_cum = net.cumsum()
    mcc = net.ewm(span=19, adjust=False).mean() - net.ewm(span=39, adjust=False).mean()
    adv_ratio = adv / total.where(total > 0)
    thrust_ratio = adv_ratio.ewm(span=10, adjust=False).mean()
    med_ret = ret.median(axis=1)

    ma_s = close.rolling(ma_short).mean()
    ma_l = close.rolling(ma_long).mean()
    den_s = ma_s.notna().sum(axis=1)
    den_l = ma_l.notna().sum(axis=1)
    pct_s = (close > ma_s).sum(axis=1) / den_s.where(den_s > 0)
    pct_l = (close > ma_l).sum(axis=1) / den_l.where(den_l > 0)

    roll_hi = close.rolling(new_high).max()
    roll_lo = close.rolling(new_high).min()
    new_highs = (close >= roll_hi).sum(axis=1)
    new_lows = (close <= roll_lo).sum(axis=1)

    # Zweig 宽度推力：任一滚动 10 日窗内 adv_ratio 的 10d-EMA 自 <0.40 升至
    # >0.615；连续达标日合并为一个事件（记录首个穿越日）。罕见事件，按设计。
    thrusts: list[dict] = []
    tlist = list(thrust_ratio.items())
    in_event = False
    for i, (d, tval) in enumerate(tlist):
        if tval is None or not (tval == tval):
            in_event = False
            continue
        win = [tlist[k][1] for k in range(max(0, i - 9), i + 1)]
        win = [v for v in win if v is not None and v == v]
        qualifies = bool(win) and min(win) < 0.40 and tval > 0.615
        if qualifies and not in_event:
            thrusts.append({"time": _ts(d),
                            "ratio": _clean(float(tval)),
                            "window_low": _clean(float(min(win)))})
        in_event = qualifies

    def g(series: pd.Series, i: int):
        v = series.iloc[i]
        return _clean(float(v)) if (v == v) else None

    series = []
    dates = list(close.index)
    for i in range(len(dates)):
        d = dates[i]
        tot = int(total.iloc[i])
        series.append({
            "time": _ts(d),
            "adv": int(adv.iloc[i]), "dec": int(dec.iloc[i]),
            "unc": int(unc.iloc[i]), "total": tot,
            "adv_ratio": g(adv_ratio, i), "med_ret": g(med_ret, i),
            "ad_cum": g(ad_cum, i), "mcclellan": g(mcc, i),
            "thrust_ratio": g(thrust_ratio, i),
            "pct_above_ma_short": g(pct_s, i),
            "pct_above_ma_long": g(pct_l, i),
            "new_highs": int(new_highs.iloc[i]),
            "new_lows": int(new_lows.iloc[i]),
        })

    latest = dict(series[-1]) if series else None
    if latest:
        latest["ma_short"] = ma_short
        latest["ma_long"] = ma_long
        latest["new_high"] = new_high
        latest["n_days"] = len(series)

    result = _clean({"ma_short": ma_short, "ma_long": ma_long, "new_high": new_high,
                     "n_days": len(series), "series": series, "latest": latest,
                     "thrusts": thrusts,
                     "params": {"thrust_low": 0.40, "thrust_high": 0.615}})
    _INTERNALS_CACHE = (mtime, result)
    return result


# --------------------------------------------------------------------------- #
# 相对强度（vs 等权市场指数）
# --------------------------------------------------------------------------- #


def relstrength(period: int = 60, ma_trend: int = 20,
                symbol: str | None = None) -> dict:
    """个股相对强度：等权市场指数序列 + 逐日跑赢指数的家数占比（breadth）
    + 全池 period 段相对收益排名；传 symbol 时附该股 RS 三线
    （归一价格 / 归一指数 / 比值）供双线图。"""
    empty = {"period": period, "ma_trend": ma_trend, "symbol": symbol,
             "n_days": 0, "n_stocks": 0, "mkt_ret_period": None,
             "median_rs_ret": None, "pct_outperformers": None,
             "index": [], "breadth": [], "ranking": [], "symbol_info": None}
    close = base.close_wide()
    if close.empty:
        return empty
    period = max(2, min(int(period), len(close) - 1))
    ma_trend = max(2, int(ma_trend))
    names = _names()

    # 等权市场指数：逐日全池收益均值，cumprod 归一到首日 1.0。
    mkt_ret_d = close.pct_change().mean(axis=1)
    idx = (1 + mkt_ret_d.fillna(0.0)).cumprod()
    idx = idx / idx.iloc[0]

    # RS 比值矩阵：close / index，再按各股首个有效日归一到 1.0（跨名可比，
    # 且保留"现值 vs 自身均线"的趋势语义）。
    rs_ratio = close.div(idx, axis=0)
    _fv = rs_ratio.apply(lambda c: c.dropna().iloc[0] if c.dropna().size else 1.0)
    rs_ratio = rs_ratio.div(_fv, axis=1)

    last = len(close) - 1
    base_i = last - period
    mkt_ret_period = idx.iloc[last] / idx.iloc[base_i] - 1
    stock_ret_period = close.iloc[last] / close.iloc[base_i] - 1
    rs_ret = stock_ret_period - mkt_ret_period

    rs_ratio_now = rs_ratio.iloc[last]
    rs_ratio_ma = rs_ratio.iloc[-ma_trend:].mean(axis=0)
    improving = rs_ratio_now > rs_ratio_ma

    # RS breadth：逐日 period 段相对收益 > 0 的家数占比。
    stock_roll = close.pct_change(period)
    mkt_roll = idx.pct_change(period)
    rs_roll = stock_roll.sub(mkt_roll, axis=0)
    den = rs_roll.notna().sum(axis=1)
    breadth = (rs_roll > 0).sum(axis=1) / den.where(den > 0)

    rows = []
    for sym in close.columns:
        r = rs_ret.get(sym)
        if r is None or not (r == r):
            continue
        rows.append({
            "symbol": sym,
            "name": names.get(sym, sym),
            "rs_ret": _clean(float(r)),
            "abs_ret": _clean(float(stock_ret_period.get(sym))),
            "rs_ratio": _clean(float(rs_ratio_now.get(sym))),
            "rs_ratio_ma": _clean(float(rs_ratio_ma.get(sym))),
            "trend": "improving" if bool(improving.get(sym, False)) else "deteriorating",
            "close": _clean(float(close.iloc[last].get(sym))),
        })
    rows.sort(key=lambda x: x["rs_ret"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    index_series = _series_of(idx)
    breadth_series = _series_of(breadth)

    n = len(rows)
    rs_rets = [x["rs_ret"] for x in rows if x["rs_ret"] is not None]
    pct_out = (sum(1 for v in rs_rets if v > 0) / n) if n else None

    symbol_info = None
    if symbol and symbol in close.columns:
        s_close = close[symbol]
        price_norm = s_close / s_close.iloc[0]
        by_sym = {x["symbol"]: x for x in rows}
        symbol_info = {
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "price_norm": _series_of(price_norm),
            "index_norm": _series_of(idx),
            "rs_line": _series_of(rs_ratio[symbol]),
            "rank": by_sym[symbol]["rank"] if symbol in by_sym else None,
            "rs_ret": by_sym[symbol]["rs_ret"] if symbol in by_sym else None,
            "abs_ret": by_sym[symbol]["abs_ret"] if symbol in by_sym else None,
            "trend": by_sym[symbol]["trend"] if symbol in by_sym else None,
        }

    return _clean({
        "period": period, "ma_trend": ma_trend, "symbol": symbol,
        "n_days": len(close), "n_stocks": n,
        "mkt_ret_period": _clean(float(mkt_ret_period)),
        "median_rs_ret": _clean(float(pd.Series(rs_rets).median())) if rs_rets else None,
        "pct_outperformers": _clean(float(pct_out)) if pct_out is not None else None,
        "index": index_series,
        "breadth": breadth_series,
        "ranking": rows,
        "symbol_info": symbol_info,
    })


# --------------------------------------------------------------------------- #
# 波动率 / 截面离散度 regime
# --------------------------------------------------------------------------- #


def volregime(window: int = 20, symbol: str | None = None) -> dict:
    """市场实现波动率（等权 RMS 口径）+ 截面离散度 + 隐含平均相关
    （由 E[Var_i] = sigma_bar^2 (1-1/n)(1-rho) 反推）的全历史序列与最新快照，
    附逐股实现波动率排名；传 symbol 时附该股波动率序列。"""
    empty = {"window": window, "symbol": symbol, "n_days": 0, "n_stocks": 0,
             "n_names": 0, "mkt_vol": None, "dispersion": None,
             "implied_corr": None, "vol_pctile": None, "corr_pctile": None,
             "mkt_vol_series": [], "dispersion_series": [],
             "implied_corr_series": [], "vol_pcts": None,
             "ranking": [], "symbol_info": None}
    close = base.close_wide()
    if close.empty:
        return empty
    window = max(5, min(int(window), len(close) - 1))
    names = _names()
    n = int(close.shape[1])
    sqrt252 = math.sqrt(252)

    rets = close.pct_change()
    per_vol = rets.rolling(window).std() * sqrt252
    mkt_var_ann = (per_vol ** 2).mean(axis=1)
    mkt_vol = mkt_var_ann.pow(0.5)

    cs_var_ann = rets.var(axis=1).rolling(window).mean() * 252.0
    dispersion = cs_var_ann.pow(0.5)

    denom = mkt_var_ann * (1.0 - 1.0 / n)
    implied_corr = 1.0 - cs_var_ann.div(denom.where(denom > 0))

    valid = mkt_vol.dropna()
    if valid.empty:
        return empty
    last = valid.index[-1]
    mkt_vol_last = float(mkt_vol.loc[last])
    disp_last = float(dispersion.loc[last]) if last in dispersion.index else None
    corr_last = float(implied_corr.loc[last]) if last in implied_corr.index else None

    vol_pctile = float((valid <= mkt_vol_last).mean())
    corr_valid = implied_corr.dropna()
    corr_pctile = (float((corr_valid <= corr_last).mean())
                   if corr_last is not None and not corr_valid.empty else None)

    vol_pcts = {
        "p25": _clean(float(valid.quantile(0.25))),
        "p50": _clean(float(valid.quantile(0.50))),
        "p75": _clean(float(valid.quantile(0.75))),
    }

    period_ret = close.pct_change(window)
    vol_last_row = per_vol.loc[last]
    rows = []
    for sym in close.columns:
        v = vol_last_row.get(sym)
        if v is None or not (v == v):
            continue
        vv = per_vol[sym].dropna()
        vov = float(vv.std()) if len(vv) > 1 else None
        r = period_ret.loc[last].get(sym) if last in period_ret.index else None
        rv = (float(r) / float(v)) if (r is not None and r == r and v) else None
        rows.append({
            "symbol": sym,
            "name": names.get(sym, sym),
            "realized_vol": _clean(float(v)),
            "vol_of_vol": _clean(vov),
            "vol_adj_ret": _clean(rv),
            "ret": _clean(float(r)) if (r is not None and r == r) else None,
            "close": _clean(float(close.iloc[-1].get(sym))),
        })
    rows.sort(key=lambda x: x["realized_vol"], reverse=True)
    vol_values = pd.Series([x["realized_vol"] for x in rows])
    for i, row in enumerate(rows):
        row["rank"] = i + 1
        row["vol_pctile"] = _clean(float((vol_values <= row["realized_vol"]).mean()))

    symbol_info = None
    if symbol and symbol in close.columns:
        by_sym = {x["symbol"]: x for x in rows}
        symbol_info = {
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "vol_series": _series_of(per_vol[symbol]),
            "mkt_vol_series": _series_of(mkt_vol),
            "realized_vol": by_sym[symbol]["realized_vol"] if symbol in by_sym else None,
            "vol_of_vol": by_sym[symbol]["vol_of_vol"] if symbol in by_sym else None,
            "rank": by_sym[symbol]["rank"] if symbol in by_sym else None,
            "vol_pctile": by_sym[symbol]["vol_pctile"] if symbol in by_sym else None,
        }

    return _clean({
        "window": window, "symbol": symbol, "n_days": len(close),
        "n_stocks": len(rows), "n_names": n,
        "mkt_vol": _clean(mkt_vol_last),
        "dispersion": _clean(disp_last),
        "implied_corr": _clean(corr_last),
        "vol_pctile": _clean(vol_pctile),
        "corr_pctile": _clean(corr_pctile),
        "mkt_vol_series": _series_of(mkt_vol),
        "dispersion_series": _series_of(dispersion),
        "implied_corr_series": _series_of(implied_corr),
        "vol_pcts": vol_pcts,
        "ranking": rows,
        "symbol_info": symbol_info,
    })


# --------------------------------------------------------------------------- #
# 波动率期限结构（vol cone）
# --------------------------------------------------------------------------- #

_VC_WINDOWS = [10, 20, 30, 60, 90, 120, 180, 252]
_VC_W_REF = 20
_VC_MIN_VALID = 30


def volcone(symbol: str = "ABNB", window: int = 20) -> dict:
    """波动率期限结构：各回看窗口（10..252 日）实现波动率 vs 自身历史分位带
    （min/p10/p25/p50/p75/p90/max），逐股按参考窗口的历史分位排名，
    slope = vol@10 − vol@120 标记短端波动抬升；传 symbol 时附全窗口 cone。"""
    empty = {"symbol": symbol, "window": window, "windows": list(_VC_WINDOWS),
             "n_days": 0, "n_names": 0, "n_stocks": 0,
             "symbol_info": None, "ranking": []}
    close = base.close_wide()
    if close.empty:
        return empty
    rets = close.pct_change()
    sqrt252 = math.sqrt(252.0)
    names = _names()

    per_vol = {W: rets.rolling(W).std() * sqrt252 for W in _VC_WINDOWS}
    ts_w = window if window in per_vol else _VC_W_REF

    def cone_rows(sym: str) -> list[dict]:
        out = []
        if sym not in close.columns:
            return out
        for W in _VC_WINDOWS:
            s = per_vol[W][sym].dropna()
            if len(s) < _VC_MIN_VALID:
                continue
            cur = float(s.iloc[-1])
            out.append({
                "window": W,
                "current": _clean(cur),
                "p_min": _clean(float(s.min())),
                "p10": _clean(float(s.quantile(0.10))),
                "p25": _clean(float(s.quantile(0.25))),
                "p50": _clean(float(s.quantile(0.50))),
                "p75": _clean(float(s.quantile(0.75))),
                "p90": _clean(float(s.quantile(0.90))),
                "p_max": _clean(float(s.max())),
                "pctile": _clean(float((s <= cur).mean())),
                "n": int(len(s)),
            })
        return out

    ref = per_vol[_VC_W_REF]
    short = per_vol[10]
    med = per_vol[120]
    rank_rows = []
    for sym in close.columns:
        s = ref[sym].dropna()
        if len(s) < _VC_MIN_VALID:
            continue
        cur = float(s.iloc[-1])
        slope = None
        s10 = short[sym].dropna()
        s120 = med[sym].dropna()
        if len(s10) >= _VC_MIN_VALID and len(s120) >= _VC_MIN_VALID:
            slope = float(s10.iloc[-1]) - float(s120.iloc[-1])
        rank_rows.append({
            "symbol": sym,
            "name": names.get(sym, sym),
            "current_vol": _clean(cur),
            "pctile": _clean(float((s <= cur).mean())),
            "slope": _clean(slope),
            "n": int(len(s)),
        })
    rank_rows.sort(key=lambda x: (x["pctile"] if x["pctile"] is not None else -1.0),
                   reverse=True)
    for i, row in enumerate(rank_rows):
        row["rank"] = i + 1

    symbol_info = None
    if symbol and symbol in close.columns:
        cs = close[symbol].dropna()
        symbol_info = {
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "n": int(cs.shape[0]),
            "cone": cone_rows(symbol),
            "vol_series": _series_of(per_vol[ts_w][symbol]),
            "raw_close": [_clean(float(v)) for v in close[symbol].tolist()],
            "times": [_ts(d) for d in close.index],
        }

    return _clean({
        "symbol": symbol,
        "window": ts_w,
        "windows": list(_VC_WINDOWS),
        "n_days": int(close.shape[0]),
        "n_names": int(close.shape[1]),
        "n_stocks": len(rank_rows),
        "symbol_info": symbol_info,
        "ranking": rank_rows,
    })


# --------------------------------------------------------------------------- #
# 截面收益离散度（选股型市场 vs 宏观同步市场）
# --------------------------------------------------------------------------- #


def dispersion(window: int = 60) -> dict:
    """截面收益离散度：逐日等权市场收益 m、截面方差 d2、二阶矩 ms2
    （恒等式 ms2 = m^2 + d2），滚动 common_share = mean(m^2)/mean(ms2)
    （宏观共同成分占比）+ 离散度-|市场收益|相关 + 逐股单因子特异波动排名。"""
    empty = {"window": window, "n_days": 0, "n_names": 0,
             "dispersion": None, "dispersion_pctile": None,
             "common_share": None, "corr_disp_absret": None,
             "mkt_vol": None, "disp_pcts": None,
             "m_series": [], "d2_series": [], "ms2_series": [],
             "dispersion_series": [], "common_share_series": [],
             "most_idiosyncratic": [], "least_idiosyncratic": []}
    close = base.close_wide()
    if close.empty:
        return empty
    window = max(20, min(int(window), len(close) - 1))
    sqrt252 = math.sqrt(252)
    n = int(close.shape[1])

    rets = close.pct_change()
    m = rets.mean(axis=1)
    ms2 = (rets ** 2).mean(axis=1)
    d2 = rets.var(axis=1, ddof=0)
    disp = d2.pow(0.5)

    minp = max(5, window // 2)
    disp_smooth = disp.rolling(window, min_periods=minp).mean()
    valid = disp_smooth.dropna()
    if valid.empty:
        return empty
    last = valid.index[-1]
    disp_last = float(disp_smooth.loc[last])
    disp_pct = float((valid <= disp_last).mean())

    m2 = m ** 2
    common_share_s = (m2.rolling(window, min_periods=minp).mean()
                      / ms2.rolling(window, min_periods=minp).mean())

    abs_m = m.abs()
    joint = pd.concat([disp_smooth, abs_m], axis=1, keys=["d", "am"]).dropna()
    corr_disp_absret = float(joint["d"].corr(joint["am"])) if len(joint) > 2 else None

    mkt_vol_s = m.rolling(window, min_periods=minp).std() * sqrt252
    mkt_vol_last = float(mkt_vol_s.loc[last]) if last in mkt_vol_s.index else None

    disp_pcts = {
        "p25": _clean(float(valid.quantile(0.25))),
        "p50": _clean(float(valid.quantile(0.50))),
        "p75": _clean(float(valid.quantile(0.75))),
    }

    # 逐股单因子特异波动：r_i − α_i − β_i·m 的 OLS 残差（均值 0 形式），
    # var(resid_i) = var(r_i)(1−R²_i) ≤ var(r_i) ⇒ idio_share = √(1−R²_i) ∈ [0,1]。
    mm = m - m.mean()
    denom = float((mm ** 2).sum())
    rc = rets.sub(rets.mean(axis=0), axis=1)
    beta = rc.mul(mm, axis=0).sum(axis=0) / denom
    sys_c = pd.DataFrame({s: beta[s] * mm for s in beta.index}, index=mm.index)
    sys_c = sys_c.reindex(columns=rets.columns)
    resid = rc - sys_c
    idio_vol = resid.std(axis=0, ddof=0).dropna()
    total_vol = rets.std(axis=0, ddof=0).dropna()
    last_close = close.iloc[-1]
    cidx = (idio_vol.index.intersection(total_vol.index)
            .intersection(last_close.dropna().index))
    cs = pd.DataFrame({
        "idio_vol": (idio_vol * sqrt252).reindex(cidx),
        "total_vol": (total_vol * sqrt252).reindex(cidx),
        "idio_share": (idio_vol / total_vol).reindex(cidx),
        "close": last_close.reindex(cidx),
    }).dropna()
    most_idio = cs.sort_values("idio_vol", ascending=False).head(10)
    least_idio = cs.sort_values("idio_vol", ascending=True).head(10)

    def cs_rows(df: pd.DataFrame) -> list[dict]:
        return [{"symbol": str(s),
                 "idio_vol": _clean(float(df.loc[s, "idio_vol"])),
                 "total_vol": _clean(float(df.loc[s, "total_vol"])),
                 "idio_share": _clean(float(df.loc[s, "idio_share"])),
                 "close": _clean(float(df.loc[s, "close"]))}
                for s in df.index]

    return _clean({
        "window": window, "n_days": len(close), "n_names": n,
        "dispersion": _clean(disp_last),
        "dispersion_pctile": _clean(disp_pct),
        "common_share": (_clean(float(common_share_s.loc[last]))
                         if last in common_share_s.index else None),
        "corr_disp_absret": _clean(corr_disp_absret),
        "mkt_vol": _clean(mkt_vol_last),
        "disp_pcts": disp_pcts,
        "m_series": _series_of(m),
        "d2_series": _series_of(d2),
        "ms2_series": _series_of(ms2),
        "dispersion_series": _series_of(disp_smooth),
        "common_share_series": _series_of(common_share_s),
        "most_idiosyncratic": cs_rows(most_idio),
        "least_idiosyncratic": cs_rows(least_idio),
    })


# --------------------------------------------------------------------------- #
# 收益持续性（自相关 / 方差比 / Hurst）
# --------------------------------------------------------------------------- #

_PERSIST_LAGS = [1, 2, 5, 10, 20]
_PERSIST_VKS = [2, 5, 10, 20]


def _acf(s: pd.Series, k: int):
    if len(s) <= k + 2:
        return None
    return _clean(float(s.autocorr(lag=k)))


def _vr(s: pd.Series, k: int):
    if len(s) < k + 3:
        return None
    v1 = float(s.var(ddof=1))
    if v1 <= 0:
        return None
    rk = s.rolling(k).sum().dropna()
    if len(rk) < 2:
        return None
    return _clean(float(rk.var(ddof=1)) / (k * v1))


def _hurst(s: pd.Series):
    """R/S 分析 Hurst 指数：块尺寸 10..N/2 对数等距取点，逐块 R/S 均值
    对块尺寸做 log-log OLS 斜率。纯手写实现（无第三方回归依赖）。"""
    vals = [float(x) for x in s.values]
    N = len(vals)
    if N < 32 or N // 2 < 10:
        return None
    lo, hi = math.log(10), math.log(N // 2)
    ns = sorted({int(round(math.exp(lo + (hi - lo) * i / 11))) for i in range(12)})
    ns = [n for n in ns if 10 <= n <= N // 2]
    if len(ns) < 3:
        return None
    xs, ys = [], []
    for n in ns:
        k = N // n
        if k < 1:
            continue
        usable = vals[:k * n]
        rs_list = []
        for b in range(k):
            block = usable[b * n:(b + 1) * n]
            m = sum(block) / n
            cum = 0.0
            cmin = 0.0
            cmax = 0.0
            sq = 0.0
            for x in block:
                d = x - m
                cum += d
                if cum < cmin:
                    cmin = cum
                if cum > cmax:
                    cmax = cum
                sq += d * d
            R = cmax - cmin
            S = math.sqrt(sq / (n - 1)) if n > 1 else 0.0
            if S > 0:
                rs_list.append(R / S)
        if rs_list:
            xs.append(math.log(n))
            ys.append(math.log(sum(rs_list) / len(rs_list)))
    if len(xs) < 3:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0:
        return None
    return _clean(num / den)


def persistence(symbol: str | None = None) -> dict:
    """收益持续性（均值回归 / 趋势）：全池逐股 ACF(rho) 滞后 1/2/5/10/20、
    Lo-MacKinlay 重叠方差比 VR(2/5/10/20)、R/S Hurst 指数；市场聚合 =
    等权逐日收益均值序列的同一套统计；ranking 按 |rho1| 降序；
    传 symbol 时附该股原始收益序列与逐滞后/逐 VR 序列。"""
    LAGS = _PERSIST_LAGS
    VKS = _PERSIST_VKS
    empty = {
        "symbol": symbol, "n_days": 0, "n_stocks": 0, "n_names": 0,
        "lags": LAGS, "vks": VKS,
        "rho1": None, "vr2": None, "hurst": None,
        "acf": [None] * len(LAGS), "vr": [None] * len(VKS),
        "mkt_acf_series": [], "mkt_vr_series": [],
        "ranking": [], "symbol_info": None,
    }
    close = base.close_wide()
    if close.empty:
        return empty
    rets = close.pct_change()
    names = _names()
    n_days = len(close)

    def _stats(s: pd.Series) -> dict | None:
        s = s.dropna()
        if len(s) < 5:
            return None
        acf = [_acf(s, k) for k in LAGS]
        vr = [_vr(s, k) for k in VKS]
        return {"acf": acf, "vr": vr, "hurst": _hurst(s),
                "rho1": acf[0], "vr2": vr[0], "n": int(len(s))}

    mkt_ret = rets.mean(axis=1).dropna()
    mkt = _stats(mkt_ret)

    def _ts_lag(i: int) -> int:
        return int((pd.Timestamp("2000-01-01")
                    + pd.Timedelta(days=int(LAGS[i]))).value // 10**9)

    def _ts_vk(i: int) -> int:
        return int((pd.Timestamp("2000-01-01")
                    + pd.Timedelta(days=int(VKS[i]))).value // 10**9)

    mkt_acf_series = ([{"time": _ts_lag(i), "value": mkt["acf"][i]}
                       for i in range(len(LAGS)) if mkt["acf"][i] is not None]
                      if mkt else [])
    mkt_vr_series = ([{"time": _ts_vk(i), "value": mkt["vr"][i]}
                      for i in range(len(VKS)) if mkt["vr"][i] is not None]
                     if mkt else [])

    rows = []
    for sym in close.columns:
        st = _stats(rets[sym])
        if st is None:
            continue
        rows.append({
            "symbol": sym, "name": names.get(sym, sym),
            "acf": st["acf"], "vr": st["vr"], "hurst": st["hurst"],
            "rho1": st["rho1"], "vr2": st["vr2"], "n": st["n"],
        })
    rows.sort(key=lambda r: (abs(r["rho1"]) if r["rho1"] is not None else -1.0),
              reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    symbol_info = None
    if symbol and symbol in close.columns:
        st = _stats(rets[symbol])
        if st is not None:
            by = {r["symbol"]: r for r in rows}
            sym_ret = rets[symbol].dropna()
            sym_acf_series = [{"time": _ts_lag(i), "value": st["acf"][i]}
                              for i in range(len(LAGS)) if st["acf"][i] is not None]
            sym_vr_series = [{"time": _ts_vk(i), "value": st["vr"][i]}
                             for i in range(len(VKS)) if st["vr"][i] is not None]
            symbol_info = {
                "symbol": symbol, "name": names.get(symbol, symbol),
                "acf": st["acf"], "vr": st["vr"], "hurst": st["hurst"],
                "rho1": st["rho1"], "vr2": st["vr2"], "n": st["n"],
                "returns": [float(x) for x in sym_ret.values],
                "acf_series": sym_acf_series, "mkt_acf_series": mkt_acf_series,
                "vr_series": sym_vr_series, "mkt_vr_series": mkt_vr_series,
                "rank": by[symbol]["rank"] if symbol in by else None,
            }

    return _clean({
        "symbol": symbol, "n_days": n_days, "n_stocks": len(rows),
        "n_names": int(close.shape[1]),
        "lags": LAGS, "vks": VKS,
        "rho1": mkt["rho1"] if mkt else None,
        "vr2": mkt["vr2"] if mkt else None,
        "hurst": mkt["hurst"] if mkt else None,
        "acf": mkt["acf"] if mkt else [None] * len(LAGS),
        "vr": mkt["vr"] if mkt else [None] * len(VKS),
        "mkt_acf_series": mkt_acf_series, "mkt_vr_series": mkt_vr_series,
        "ranking": rows, "symbol_info": symbol_info,
    })


# --------------------------------------------------------------------------- #
# 日历季节性（月份 / 星期）
# --------------------------------------------------------------------------- #


def seasonality(symbol: str | None = None) -> dict:
    """日历季节性：逐股与等权市场聚合的日收益按月份（1-12）与星期（周一~五）
    分组统计（均值 / 胜率 / t 值 / 样本 std / 样本数），seasonality_strength =
    月度均值的总体 std，best/worst_month 为月度均值 argmax/argmin；
    ranking 按强度降序；传 symbol 时附该股月度序列。"""
    empty = {
        "symbol": symbol, "n_days": 0, "n_stocks": 0, "n_names": 0,
        "cur_month": None, "cur_dow": None,
        "overall_mean": None, "seasonality_strength": None,
        "best_month": None, "worst_month": None,
        "monthly_mean": [None] * 12, "monthly_win": [None] * 12,
        "monthly_t": [None] * 12, "monthly_std": [None] * 12, "monthly_n": [0] * 12,
        "dow_mean": [None] * 5, "dow_win": [None] * 5, "dow_n": [0] * 5,
        "mkt_monthly_series": [], "mkt_win_series": [], "mkt_dow_series": [],
        "ranking": [], "symbol_info": None,
    }
    close = base.close_wide()
    if close.empty:
        return empty
    rets = close.pct_change()
    idx = close.index
    last_dt = pd.Timestamp(idx[-1])
    cur_month = int(last_dt.month)
    cur_dow = int(last_dt.dayofweek)
    names = _names()

    def _ts_month(m: int) -> int:
        return _ts(f"2000-{m:02d}-01")

    def _ts_dow(d: int) -> int:
        # d ∈ 0..4 → 名义一周的周一..周五（2000-01-03 是周一）
        return int((pd.Timestamp("2000-01-03")
                    + pd.Timedelta(days=int(d))).value // 10**9)

    def _stats(s: pd.Series):
        s = s.dropna()
        m_mean: list = [None] * 12
        m_win: list = [None] * 12
        m_t: list = [None] * 12
        m_std: list = [None] * 12
        m_n: list = [0] * 12
        d_mean: list = [None] * 5
        d_win: list = [None] * 5
        d_n: list = [0] * 5
        if len(s) == 0:
            return (m_mean, m_win, m_t, m_std, m_n, d_mean, d_win, d_n,
                    None, None, None, None)
        dt = pd.to_datetime(s.index)
        for m, x in s.groupby(dt.month.values):
            i = int(m) - 1
            n = len(x)
            mu = float(x.mean())
            m_mean[i] = _clean(mu)
            m_win[i] = _clean(float((x > 0).mean()))
            m_n[i] = int(n)
            if n > 1:
                sd = float(x.std(ddof=1))
                m_std[i] = _clean(sd)
                if sd > 0:
                    m_t[i] = _clean(mu / (sd / (n ** 0.5)))
        for d, x in s.groupby(dt.dayofweek.values):
            if 0 <= d <= 4:
                i = int(d)
                d_mean[i] = _clean(float(x.mean()))
                d_win[i] = _clean(float((x > 0).mean()))
                d_n[i] = int(len(x))
        overall = float(s.mean())
        present = [v for v in m_mean if v is not None]
        if len(present) >= 2:
            mean_of = sum(present) / len(present)
            strength = (sum((v - mean_of) ** 2 for v in present) / len(present)) ** 0.5
        else:
            strength = None
        best = worst = None
        if present:
            bi = max(range(12), key=lambda i: m_mean[i] if m_mean[i] is not None else -1e18)
            wi = min(range(12), key=lambda i: m_mean[i] if m_mean[i] is not None else 1e18)
            best, worst = bi + 1, wi + 1
        return (m_mean, m_win, m_t, m_std, m_n, d_mean, d_win, d_n,
                _clean(overall), _clean(strength), best, worst)

    mkt_ret = rets.mean(axis=1).dropna()
    (mm_m, mw_m, mt_m, msd_m, mn_m, dm_m, dw_m, dn_m,
     mkt_overall, mkt_strength, mkt_best, mkt_worst) = _stats(mkt_ret)

    mkt_monthly_series = [{"time": _ts_month(m), "value": mm_m[m - 1]}
                          for m in range(1, 13) if mm_m[m - 1] is not None]
    mkt_win_series = [{"time": _ts_month(m), "value": mw_m[m - 1]}
                      for m in range(1, 13) if mw_m[m - 1] is not None]
    mkt_dow_series = [{"time": _ts_dow(d), "value": dm_m[d]}
                      for d in range(5) if dm_m[d] is not None]

    rows = []
    for sym in close.columns:
        (mm, mw, mt, msd, mn, dm, dw, dn,
         overall, strength, best, worst) = _stats(rets[sym])
        if overall is None:
            continue
        rows.append({
            "symbol": sym, "name": names.get(sym, sym),
            "overall_mean": overall, "seasonality_strength": strength,
            "best_month": best, "worst_month": worst,
            "cur_month_mean": _clean(mm[cur_month - 1]) if cur_month else None,
            "monthly_mean": mm, "monthly_win": mw, "monthly_t": mt,
            "monthly_std": msd, "monthly_n": mn,
            "dow_mean": dm, "dow_win": dw, "dow_n": dn,
        })
    rows.sort(key=lambda r: (r["seasonality_strength"]
                             if r["seasonality_strength"] is not None else -1.0),
              reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    symbol_info = None
    if symbol and symbol in close.columns:
        (mm, mw, mt, msd, mn, dm, dw, dn,
         overall, strength, best, worst) = _stats(rets[symbol])
        by = {r["symbol"]: r for r in rows}
        sym_monthly_series = [{"time": _ts_month(m), "value": mm[m - 1]}
                              for m in range(1, 13) if mm[m - 1] is not None]
        symbol_info = {
            "symbol": symbol, "name": names.get(symbol, symbol),
            "overall_mean": overall, "seasonality_strength": strength,
            "best_month": best, "worst_month": worst,
            "cur_month_mean": _clean(mm[cur_month - 1]) if cur_month else None,
            "monthly_mean": mm, "monthly_win": mw, "monthly_t": mt,
            "monthly_std": msd, "monthly_n": mn,
            "dow_mean": dm, "dow_win": dw, "dow_n": dn,
            "monthly_series": sym_monthly_series,
            "mkt_monthly_series": mkt_monthly_series,
            "rank": by[symbol]["rank"] if symbol in by else None,
        }

    return _clean({
        "symbol": symbol, "n_days": len(close), "n_stocks": len(rows),
        "n_names": int(close.shape[1]),
        "cur_month": cur_month, "cur_dow": cur_dow,
        "overall_mean": mkt_overall, "seasonality_strength": mkt_strength,
        "best_month": mkt_best, "worst_month": mkt_worst,
        "monthly_mean": mm_m, "monthly_win": mw_m, "monthly_t": mt_m,
        "monthly_std": msd_m, "monthly_n": mn_m,
        "dow_mean": dm_m, "dow_win": dw_m, "dow_n": dn_m,
        "mkt_monthly_series": mkt_monthly_series,
        "mkt_win_series": mkt_win_series, "mkt_dow_series": mkt_dow_series,
        "ranking": rows, "symbol_info": symbol_info,
    })


# --------------------------------------------------------------------------- #
# 隔夜 / 日内收益分解
# --------------------------------------------------------------------------- #

_ONI_MIN_DAYS = 60


def _shp(s: pd.Series):
    sd = float(s.std(ddof=1))
    return (float(s.mean()) / sd * math.sqrt(252.0)) if sd > 0 else None


def _var_split(ln_on, ln_in, ln_daily) -> dict | None:
    """对数收益方差分解：Var(ln_on)/Var(ln_daily) + Var(ln_in)/Var(ln_daily)
    + 交叉项 2·Cov(ln_on, ln_in)/Var(ln_daily)，三项恒等于 1。"""
    if len(ln_daily) < 2:
        return None
    vd = float(ln_daily.var())
    if not vd or vd != vd:
        return None
    return {
        "overnight_share": _clean(float(ln_on.var()) / vd),
        "intraday_share": _clean(float(ln_in.var()) / vd),
        "cross_term": _clean(2.0 * float(ln_on.cov(ln_in)) / vd),
        "method": ("log-return: Var(ln_on)/Var(ln_daily); "
                   "overnight_share + intraday_share + cross_term == 1 "
                   "(cross_term < 0 = overnight/intraday offset, > 0 = amplify)"),
    }


def _gap_stats(on, high, low, prev_close, eps: float = 1e-6) -> dict | None:
    """跳空行为：上跳缺口（open>prev_close）当日 low 回补至 ≤ prev_close
    视为已回补，下跳缺口对称；输出跳空频率 / 回补率 / 平均绝对跳空幅度。"""
    n = len(on)
    if not n:
        return None
    up = on > eps
    dn = on < -eps
    n_up, n_dn = int(up.sum()), int(dn.sum())
    n_gap = n_up + n_dn
    fill_up = int((low[up] <= prev_close[up]).sum())
    fill_dn = int((high[dn] >= prev_close[dn]).sum())
    gapping = on[on.abs() > eps]
    return {
        "gap_freq": _clean(n_gap / n),
        "gap_up_freq": _clean(n_up / n),
        "gap_dn_freq": _clean(n_dn / n),
        "no_gap_freq": _clean((n - n_gap) / n),
        "mean_abs_gap": _clean(float(gapping.abs().mean())) if len(gapping) else None,
        "fill_rate": _clean((fill_up + fill_dn) / n_gap) if n_gap else None,
        "fill_rate_up": _clean(fill_up / n_up) if n_up else None,
        "fill_rate_dn": _clean(fill_dn / n_dn) if n_dn else None,
    }


def overnight(symbol: str | None = None, window: int = 126) -> dict:
    """隔夜/日内收益分解（全日线历史）：overnight = open/prev_close − 1，
    intraday = close/open − 1（两者复利恒等于日收益）；输出市场等权聚合的
    三条累计曲线、逐股年化收益 / Sharpe / 方差分解份额 / 跳空统计排名
    （按 overnight_sharpe 降序）；传 symbol 时附该股累计曲线与滚动 Sharpe
    及原始对齐数组。"""
    empty = {
        "symbol": symbol, "window": window, "n_days": 0, "n_stocks": 0, "n_names": 0,
        "market": None,
        "mkt_on_series": [], "mkt_in_series": [], "mkt_da_series": [],
        "mkt_cum_on_series": [], "mkt_cum_in_series": [], "mkt_cum_total_series": [],
        "ranking": [], "symbol_info": None,
    }
    ohl = base.ohl_wide()
    close = ohl["close"]
    if close.empty:
        return empty
    window = max(20, min(int(window), len(close) - 1))
    open_, high, low = ohl["open"], ohl["high"], ohl["low"]
    n_names = int(close.shape[1])
    names = _names()
    sqrt252 = math.sqrt(252.0)

    prev_close = close.shift(1)
    overnight_r = (open_ / prev_close - 1.0).replace(
        [float("inf"), float("-inf")], float("nan"))
    intraday_r = (close / open_ - 1.0).replace(
        [float("inf"), float("-inf")], float("nan"))
    daily = close.pct_change()

    def _oni_stats(d: pd.DataFrame) -> dict | None:
        n = len(d)
        if n < _ONI_MIN_DAYS:
            return None
        on, in_, da = d["on"], d["in"], d["da"]
        ln_on = (1.0 + on).map(math.log)
        ln_in = (1.0 + in_).map(math.log)
        ln_da = ln_on + ln_in
        vs = _var_split(ln_on, ln_in, ln_da) or {}
        gs = _gap_stats(d["on"], d["hi"], d["lo"], d["pc"]) or {}
        return {
            "ann_overnight": _clean(float(on.mean()) * 252),
            "ann_intraday": _clean(float(in_.mean()) * 252),
            "ann_total": _clean(float(da.mean()) * 252),
            "overnight_sharpe": _clean(_shp(on)),
            "intraday_sharpe": _clean(_shp(in_)),
            "overnight_share": vs.get("overnight_share"),
            "intraday_share": vs.get("intraday_share"),
            "cross_term": vs.get("cross_term"),
            "gap_freq": gs.get("gap_freq"),
            "fill_rate": gs.get("fill_rate"),
            "mean_abs_gap": gs.get("mean_abs_gap"),
            "n": int(n),
        }

    mkt_on = overnight_r.mean(axis=1)
    mkt_in = intraday_r.mean(axis=1)
    mkt_da = daily.mean(axis=1)

    def series_of(s: pd.Series) -> list[dict]:
        return [{"time": _ts(t), "value": _clean(float(v))}
                for t, v in s.items()
                if float(v) == float(v) and abs(float(v)) != float("inf")]

    def cum_series(s: pd.Series) -> list[dict]:
        v = s.dropna()
        if v.empty:
            return []
        cum = (1.0 + v).cumprod()
        return [{"time": _ts(t), "value": _clean(float(x))} for t, x in cum.items()]

    mkt_on_series = series_of(mkt_on)
    mkt_in_series = series_of(mkt_in)
    mkt_da_series = series_of(mkt_da)
    mkt_cum_on = cum_series(mkt_on)
    mkt_cum_in = cum_series(mkt_in)
    mkt_cum_total = cum_series(mkt_da)

    mkt_df = pd.DataFrame({"on": mkt_on, "in": mkt_in, "da": mkt_da}).dropna()
    market = None
    if len(mkt_df) >= 2:
        on, in_, da = mkt_df["on"], mkt_df["in"], mkt_df["da"]
        ln_on = (1.0 + on).map(math.log)
        ln_in = (1.0 + in_).map(math.log)
        ln_da = ln_on + ln_in
        mvs = _var_split(ln_on, ln_in, ln_da) or {}
        market = {
            "ann_overnight": _clean(float(on.mean()) * 252),
            "ann_intraday": _clean(float(in_.mean()) * 252),
            "ann_total": _clean(float(da.mean()) * 252),
            "overnight_sharpe": _clean(_shp(on)),
            "intraday_sharpe": _clean(_shp(in_)),
            "overnight_share": mvs.get("overnight_share"),
            "intraday_share": mvs.get("intraday_share"),
            "cross_term": mvs.get("cross_term"),
            "n": int(len(mkt_df)),
        }

    rows = []
    sym_frames: dict[str, pd.DataFrame] = {}
    for sym in close.columns:
        d = pd.DataFrame({
            "on": overnight_r[sym], "in": intraday_r[sym], "da": daily[sym],
            "op": open_[sym], "cl": close[sym], "pc": prev_close[sym],
            "hi": high[sym], "lo": low[sym],
        }).dropna()
        if len(d) < _ONI_MIN_DAYS:
            continue
        st = _oni_stats(d)
        if st is None:
            continue
        sym_frames[sym] = d
        rows.append({"symbol": sym, "name": names.get(sym, sym), **st})

    rows.sort(key=lambda r: (r["overnight_sharpe"] if r["overnight_sharpe"] is not None
                             else float("-inf")), reverse=True)
    by_sym = {r["symbol"]: r for r in rows}
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    symbol_info = None
    if symbol and symbol in sym_frames:
        d = sym_frames[symbol]
        st = _oni_stats(d) or {}
        roll_mean = d["on"].rolling(window).mean()
        roll_std = d["on"].rolling(window).std(ddof=1)
        roll_sharpe = roll_mean / roll_std * sqrt252
        cum_on = (1.0 + d["on"]).cumprod()
        cum_in = (1.0 + d["in"]).cumprod()
        cum_da = (1.0 + d["da"]).cumprod()
        times = [_ts(t) for t in d.index]

        def arr(col: str) -> list[float]:
            return [float(x) for x in d[col].values]

        def cum_line(cum: pd.Series) -> list[dict]:
            return [{"time": times[i], "value": _clean(float(cum.iloc[i]))}
                    for i in range(len(d))]

        symbol_info = {
            "symbol": symbol, "name": names.get(symbol, symbol), "window": window,
            **st,
            "rank": by_sym[symbol]["rank"] if symbol in by_sym else None,
            "cum_on_series": cum_line(cum_on),
            "cum_in_series": cum_line(cum_in),
            "cum_total_series": cum_line(cum_da),
            "on_sharpe_series": series_of(roll_sharpe),
            "on": arr("on"), "in": arr("in"), "daily": arr("da"),
            "open": arr("op"), "close": arr("cl"), "prev_close": arr("pc"),
            "high": arr("hi"), "low": arr("lo"),
            "times": times,
        }

    return _clean({
        "symbol": symbol, "window": window,
        "n_days": len(close), "n_stocks": len(rows), "n_names": n_names,
        "market": market,
        "mkt_on_series": mkt_on_series, "mkt_in_series": mkt_in_series,
        "mkt_da_series": mkt_da_series,
        "mkt_cum_on_series": mkt_cum_on, "mkt_cum_in_series": mkt_cum_in,
        "mkt_cum_total_series": mkt_cum_total,
        "ranking": rows, "symbol_info": symbol_info,
    })
