"""港股个股级风险分析服务（/api/us-analytics/risk/* 的计算层）。

七个分析函数，全部基于共享数据层 hk_analytics_base 的 day × symbol 宽表：
- tailrisk          尾部风险与收益分布形态（VaR/CVaR/偏度/峰度）
- drawdown          回撤与路径风险（水下曲线/最长水下天数）
- beta              滚动 Beta 与市场模型方差分解
- pairs_scan        配对协整性扫描（全宇宙排序）
- pairs_detail      指定配对的协整细节（ADF/半衰期/spread 序列）
- risk_adj_ranking  风险调整收益截面排名（Sharpe/Sortino/Calmar）
- effbets           有效下注数（相关矩阵特征谱参与度）
- liquidity         Amihud 非流动性截面与时序

返回结构与前端页面契约一一对应；所有序列的时间字段为 'YYYY-MM-DD' 字符串，
所有数值经 _clean 递归转换（numpy 标量转原生、nan/inf 转 None）。
无参的重截面计算按 (函数, 参数, 数据 mtime) 做模块级缓存。
"""
from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
import pandas as pd

from app.services.hk_analytics_base import (
    HISTORY_PATH,
    close_wide,
    dvol_wide,
    snapshot_frame,
)

__all__ = [
    "tailrisk",
    "drawdown",
    "beta",
    "pairs_scan",
    "pairs_detail",
    "risk_adj_ranking",
    "effbets",
    "liquidity",
]

SQRT252 = math.sqrt(252.0)
ANN = 252


# --------------------------------------------------------------------------- #
# 工具：清洗 / 名称表 / 缓存
# --------------------------------------------------------------------------- #

def _clean(obj: Any) -> Any:
    """递归转 JSON 安全结构：numpy 标量转 Python 原生，nan/inf 转 None。"""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return bool(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (str,)):
        return str(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, np.ndarray)):
        return [_clean(v) for v in obj]
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return _clean(item())
        except Exception:  # noqa: BLE001
            return None
    return obj


def _name_map() -> dict[str, str]:
    """symbol -> 公司名（来自最新截面快照，mtime 失效缓存）。"""
    global _NAMES, _NAMES_MTIME
    mtime = os.path.getmtime(HISTORY_PATH)
    if _NAMES is None or _NAMES_MTIME != mtime:
        try:
            snap = snapshot_frame()
            cols = [c for c in ("symbol", "name") if c in snap.columns]
            _NAMES = (
                snap[cols].drop_duplicates("symbol")
                .set_index("symbol")["name"].to_dict()
                if cols else {}
            )
        except Exception:  # noqa: BLE001
            _NAMES = {}
        _NAMES_MTIME = mtime
    return _NAMES


_NAMES: dict[str, str] | None = None
_NAMES_MTIME: float | None = None

# 模块级结果缓存：(key, 数据 mtime) -> 结果 dict；数据文件更新即失效。
_CACHE: dict[tuple, tuple[float, dict]] = {}


def _cached(key: tuple, build) -> dict:
    """按 (key, history mtime) 缓存重计算结果。"""
    mtime = os.path.getmtime(HISTORY_PATH)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    val = build()
    _CACHE[key] = (mtime, val)
    return val


def _series_of(s: pd.Series) -> list[dict]:
    """pd.Series -> [{time: 'YYYY-MM-DD', value: float}, ...]（跳过 nan）。"""
    return [
        {"time": str(d), "value": _clean(float(v))}
        for d, v in s.items()
        if v == v
    ]


def _ts(label) -> str:
    try:
        return str(pd.Timestamp(label).date())
    except Exception:  # noqa: BLE001
        return str(label)


# --------------------------------------------------------------------------- #
# 1. 尾部风险
# --------------------------------------------------------------------------- #

_TAIL_METRIC_KEYS = (
    "mean_ret", "vol", "skew", "excess_kurt", "var95", "var99",
    "cvar95", "cvar99", "max_loss", "max_gain", "downside_dev",
    "sortino", "tail_freq_2s", "tail_freq_3s",
)


def _col_tail_metrics(s: pd.Series) -> dict | None:
    """单票全历史尾部指标（日收益序列）。损失以正数幅度表示（VaR 3% = 0.03）。"""
    x = s.dropna()
    if len(x) < 30:
        return None
    mu = float(x.mean())
    sd = float(x.std())
    if not sd or sd != sd:
        return None
    z = (x - mu) / sd
    q05 = float(x.quantile(0.05))
    q01 = float(x.quantile(0.01))
    tail5 = x[x <= q05]
    tail1 = x[x <= q01]
    var95 = -q05
    var99 = -q01
    cvar95 = -float(tail5.mean()) if len(tail5) else var95
    cvar99 = -float(tail1.mean()) if len(tail1) else var99
    neg = x[x < 0]
    ddev = float(neg.std() * SQRT252) if len(neg) > 1 else None
    mean_ann = mu * ANN
    sortino = (mean_ann / ddev) if (ddev and ddev > 0) else None
    return {
        "mean_ret": _clean(mean_ann),
        "vol": _clean(sd * SQRT252),
        "skew": _clean(float((z ** 3).mean())),
        "excess_kurt": _clean(float((z ** 4).mean() - 3.0)),
        "var95": _clean(var95), "var99": _clean(var99),
        "cvar95": _clean(cvar95), "cvar99": _clean(cvar99),
        "max_loss": _clean(-float(x.min())),
        "max_gain": _clean(float(x.max())),
        "downside_dev": _clean(ddev),
        "sortino": _clean(sortino),
        "tail_freq_2s": _clean(float((z.abs() > 2.0).mean())),
        "tail_freq_3s": _clean(float((z.abs() > 3.0).mean())),
    }


def _rolling_tail(s: pd.Series, win: int):
    """滚动窗口 VaR95 / CVaR95 / 偏度 / 超额峰度时序。"""
    out_var, out_cvar, out_skew, out_kurt = [], [], [], []
    vals = s.values
    idx = s.index
    for i in range(win - 1, len(vals)):
        w = vals[i - win + 1: i + 1]
        w = w[~pd.isna(w)]
        if len(w) < win // 2:
            continue
        mu = w.mean()
        sd = w.std()
        if not sd or sd != sd:
            continue
        day = _ts(idx[i])
        q05 = pd.Series(w).quantile(0.05)
        tail = w[w <= q05]
        out_var.append({"time": day, "value": _clean(float(-q05))})
        out_cvar.append({"time": day, "value": _clean(
            float(-tail.mean()) if len(tail) else float(-q05))})
        zw = (w - mu) / sd
        out_skew.append({"time": day, "value": _clean(float((zw ** 3).mean()))})
        out_kurt.append({"time": day, "value": _clean(float((zw ** 4).mean() - 3.0))})
    return out_var, out_cvar, out_skew, out_kurt


def tailrisk(window: int = 63, symbol: str | None = None) -> dict:
    """尾部风险与收益分布形态（全历史口径）。

    逐票日收益序列计算标准化矩（偏度/超额峰度）、历史 VaR/CVaR（95%/99%）、
    下行偏差与 Sortino；市场聚合为等权截面日收益。快照指标用全历史，
    滚动序列（window 日 VaR/CVaR/偏度/峰度）展示尾部风险演化。
    损失一律为正幅度（VaR 3% = 0.03）。按 CVaR95 降序排名（最易崩的在前）。

    返回顶层键：window, symbol, n_days, n_stocks, n_names,
    mean_ret, vol, skew, excess_kurt, var95, var99, cvar95, cvar99,
    max_loss, max_gain, downside_dev, sortino, tail_freq_2s, tail_freq_3s,
    var95_series, cvar95_series, skew_series, kurt_series,
    ranking, symbol_info。
    """
    def build() -> dict:
        empty = {"window": window, "symbol": symbol, "n_days": 0, "n_stocks": 0,
                 "n_names": 0, "mean_ret": None, "vol": None, "skew": None,
                 "excess_kurt": None, "var95": None, "var99": None,
                 "cvar95": None, "cvar99": None, "max_loss": None, "max_gain": None,
                 "downside_dev": None, "sortino": None,
                 "tail_freq_2s": None, "tail_freq_3s": None,
                 "var95_series": [], "cvar95_series": [],
                 "skew_series": [], "kurt_series": [],
                 "ranking": [], "symbol_info": None}
        close = close_wide()
        if close.empty:
            return _clean(empty)
        window_c = max(21, min(int(window), len(close) - 1))
        rets = close.pct_change()
        n = int(close.shape[1])
        names = _name_map()

        # 逐票全历史指标，按 CVaR95 降序（最崩为主在前）
        rows = []
        for sym in close.columns:
            m = _col_tail_metrics(rets[sym])
            if m is None:
                continue
            m["symbol"] = sym
            m["name"] = names.get(sym, sym)
            m["close"] = _clean(float(close.iloc[-1].get(sym)))
            rows.append(m)
        rows.sort(key=lambda r: (r["cvar95"] if r["cvar95"] is not None else -1.0),
                  reverse=True)
        cvar_vals = pd.Series([r["cvar95"] for r in rows if r["cvar95"] is not None])
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            r["cvar_pctile"] = (_clean(float((cvar_vals <= r["cvar95"]).mean()))
                                if r["cvar95"] is not None else None)

        # 市场聚合 = 等权截面日收益
        mkt_ret = rets.mean(axis=1)
        mkt = _col_tail_metrics(mkt_ret) or {}
        mv, mcv, msk, mku = _rolling_tail(mkt_ret, window_c)

        symbol_info = None
        if symbol and symbol in close.columns:
            sm = _col_tail_metrics(rets[symbol])
            if sm:
                sv, scv, ssk, sku = _rolling_tail(rets[symbol], window_c)
                by = {r["symbol"]: r for r in rows}
                symbol_info = {
                    "symbol": symbol, "name": names.get(symbol, symbol),
                    **{k: sm[k] for k in _TAIL_METRIC_KEYS},
                    "window": window_c,
                    "var95_series": sv, "cvar95_series": scv,
                    "skew_series": ssk, "kurt_series": sku,
                    "mkt_cvar95_series": mcv,
                    "rank": by[symbol]["rank"] if symbol in by else None,
                    "cvar_pctile": by[symbol]["cvar_pctile"] if symbol in by else None,
                }

        return _clean({
            "window": window_c, "symbol": symbol, "n_days": len(close),
            "n_stocks": len(rows), "n_names": n,
            **{k: mkt.get(k) for k in _TAIL_METRIC_KEYS},
            "var95_series": mv, "cvar95_series": mcv,
            "skew_series": msk, "kurt_series": mku,
            "ranking": rows, "symbol_info": symbol_info,
        })

    return _cached(("tailrisk", int(window), symbol), build)


# --------------------------------------------------------------------------- #
# 2. 回撤
# --------------------------------------------------------------------------- #

_DD_THRESH = -1e-9
_DD_METRIC_KEYS = ("max_dd", "current_dd", "underwater_pct", "longest_dd_days",
                   "max_dd_date", "recovery_date", "recovered")


def _longest_run(below) -> int:
    longest = cur = 0
    for b in below:
        cur = cur + 1 if b else 0
        if cur > longest:
            longest = cur
    return int(longest)


def _col_drawdown(s: pd.Series) -> dict | None:
    """单票全历史回撤统计（价格序列）。深度为正幅度（45% 回撤 = 0.45）。"""
    px = s.dropna()
    if len(px) < 30:
        return None
    dd = px / px.cummax() - 1.0          # 恒 <= 0
    below = (dd < _DD_THRESH).values
    trough_i = int(dd.values.argmin())
    after = dd.iloc[trough_i:]
    rec = after[after >= _DD_THRESH]
    recovery_date = _ts(rec.index[0]) if len(rec) else None
    return {
        "max_dd": _clean(-float(dd.min())),
        "current_dd": _clean(-float(dd.iloc[-1])),
        "underwater_pct": _clean(float(below.mean())),
        "longest_dd_days": _longest_run(below),
        "max_dd_date": _ts(px.index[trough_i]),
        "recovery_date": recovery_date,
        "recovered": recovery_date is not None,
    }


def _rolling_maxdd(series: pd.Series, win: int) -> list[dict]:
    out = []
    v = series.values
    ix = series.index
    for i in range(win - 1, len(v)):
        w = v[i - win + 1: i + 1]
        peak = pd.Series(w).cummax().values
        dd_w = w / peak - 1.0
        out.append({"time": _ts(ix[i]), "value": _clean(float(-dd_w.min()))})
    return out


def drawdown(symbol: str | None = None, window: int = 63) -> dict:
    """回撤与路径风险（全历史口径）。

    回撤取决于收益的「顺序」而非仅分布：逐票由运行峰值（cummax）得水下路径
    （price/peak - 1，恒 <= 0）、最深谷底、水下时长与是否已修复；深度为正幅度。
    市场聚合 = 每票在其首个有效收盘日归一到 1 的等权指数。

    symbol 为 None 时返回全票回撤汇总表（ranking，按 max_dd 降序）+
    可选票清单（symbols）；指定 symbol 时另附个股水下时序与滚动最大回撤。

    返回顶层键：window, symbol, n_days, n_stocks, n_names, symbols,
    max_dd, current_dd, underwater_pct, longest_dd_days, max_dd_date,
    underwater_series, rolling_maxdd_series, ranking, symbol_info。
    """
    def build() -> dict:
        empty = {"window": window, "symbol": symbol, "n_days": 0, "n_stocks": 0,
                 "n_names": 0, "symbols": [],
                 "max_dd": None, "current_dd": None,
                 "underwater_pct": None, "longest_dd_days": None,
                 "max_dd_date": None,
                 "underwater_series": [], "rolling_maxdd_series": [],
                 "ranking": [], "symbol_info": None}
        close = close_wide()
        if close.empty:
            return _clean(empty)
        window_c = max(21, min(int(window), len(close) - 1))
        n = int(close.shape[1])
        names = _name_map()

        # 逐票回撤统计，按 max_dd 降序（跌得最狠在前）
        rows = []
        for sym in close.columns:
            m = _col_drawdown(close[sym])
            if m is None:
                continue
            m["symbol"] = sym
            m["name"] = names.get(sym, sym)
            m["close"] = _clean(float(close.iloc[-1].get(sym)))
            rows.append(m)
        rows.sort(key=lambda r: (r["max_dd"] if r["max_dd"] is not None else -1.0),
                  reverse=True)
        dd_vals = pd.Series([r["max_dd"] for r in rows if r["max_dd"] is not None])
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            r["dd_pctile"] = (_clean(float((dd_vals <= r["max_dd"]).mean()))
                              if r["max_dd"] is not None else None)

        # 市场 = 等权指数（每票自首个有效收盘归一为 1）
        first = close.bfill().iloc[0]
        idx = close.div(first).mean(axis=1).dropna()
        idx_dd = idx / idx.cummax() - 1.0      # 市场水下路径（恒 <= 0）
        underwater_series = [
            {"time": _ts(idx.index[i]), "value": _clean(float(idx_dd.iloc[i]))}
            for i in range(len(idx))
        ]
        rolling_maxdd_series = _rolling_maxdd(idx, window_c)
        mkt_below = (idx_dd < _DD_THRESH).values
        mkt_trough = int(idx_dd.values.argmin())

        symbol_info = None
        if symbol and symbol in close.columns:
            sm = _col_drawdown(close[symbol])
            if sm:
                px = close[symbol].dropna()
                sym_dd = px / px.cummax() - 1.0
                sym_underwater = [
                    {"time": _ts(px.index[i]), "value": _clean(float(sym_dd.iloc[i]))}
                    for i in range(len(px))
                ]
                by = {r["symbol"]: r for r in rows}
                symbol_info = {
                    "symbol": symbol, "name": names.get(symbol, symbol),
                    **{k: sm[k] for k in _DD_METRIC_KEYS},
                    "underwater_series": sym_underwater,
                    "mkt_underwater_series": underwater_series,
                    "rank": by[symbol]["rank"] if symbol in by else None,
                    "dd_pctile": by[symbol]["dd_pctile"] if symbol in by else None,
                }

        return _clean({
            "window": window_c, "symbol": symbol, "n_days": len(close),
            "n_stocks": len(rows), "n_names": n,
            "symbols": sorted(str(c) for c in close.columns),
            "max_dd": _clean(-float(idx_dd.min())),
            "current_dd": _clean(-float(idx_dd.iloc[-1])),
            "underwater_pct": _clean(float(mkt_below.mean())),
            "longest_dd_days": _longest_run(mkt_below),
            "max_dd_date": _ts(idx.index[mkt_trough]),
            "underwater_series": underwater_series,
            "rolling_maxdd_series": rolling_maxdd_series,
            "ranking": rows, "symbol_info": symbol_info,
        })

    return _cached(("drawdown", symbol, int(window)), build)


# --------------------------------------------------------------------------- #
# 3. Beta / 市场模型
# --------------------------------------------------------------------------- #

def _ols_market_model(r_s: pd.Series, r_m: pd.Series, min_n: int = 30) -> dict | None:
    """OLS 市场模型回归 r_s = alpha + beta * r_m + eps（对齐日，ddof=1）。

    方差分解精确成立：var(r_s) = beta^2 * var(r_m) + var(eps)，
    单变量含截距 OLS 有 R^2 = corr^2。
    """
    df = pd.concat([r_s, r_m], axis=1, keys=["s", "m"]).dropna()
    n = len(df)
    if n < min_n:
        return None
    s, m = df["s"], df["m"]
    var_m = float(m.var(ddof=1))
    if var_m <= 0:
        return None
    cov_sm = float(s.cov(m))
    beta_v = cov_sm / var_m
    alpha_v = float(s.mean() - beta_v * m.mean())
    corr = float(s.corr(m))
    r2 = corr * corr
    eps = s - (alpha_v + beta_v * m)
    var_eps = float(eps.var(ddof=1))
    var_s = float(s.var(ddof=1))
    return {
        "beta": _clean(beta_v), "alpha": _clean(alpha_v), "corr": _clean(corr),
        "r2": _clean(r2), "n": int(n),
        "var_m": _clean(var_m), "var_eps": _clean(var_eps), "var_s": _clean(var_s),
        "sys_vol": _clean(abs(beta_v) * math.sqrt(var_m)),
        "idio_vol": _clean(math.sqrt(max(var_eps, 0.0))),
        "tot_vol": _clean(math.sqrt(max(var_s, 0.0))),
    }


def beta(symbol: str | None = None, window: int = 126) -> dict:
    """滚动 Beta / 市场模型方差分解（系统性风险口径）。

    对每票拟合市场模型 r_s = alpha + beta * r_m + eps（OLS；市场 = 全池等权
    日收益），报告 beta / alpha / R^2 / corr 及方差分解
    sigma_s^2 = beta^2 * sigma_m^2 + sigma_eps^2，按长期 beta 降序排名。
    指定 symbol 时另附滚动（trailing window）beta / alpha / R^2 序列与
    个股 vs 等权指数的归一化价格双线。

    返回顶层键：symbol, window, n_days, n_stocks, n_names, mkt_vol,
    mkt_mean_ret, median_beta, n_aggressive, n_defensive,
    index, ranking, symbol_info。
    """
    def build() -> dict:
        empty = {
            "symbol": symbol, "window": window, "n_days": 0, "n_stocks": 0,
            "n_names": 0, "mkt_vol": None, "mkt_mean_ret": None,
            "median_beta": None, "n_aggressive": None, "n_defensive": None,
            "index": [], "ranking": [], "symbol_info": None,
        }
        close = close_wide()
        if close.empty:
            return _clean(empty)
        window_c = max(20, min(int(window), len(close) - 1))
        rets = close.pct_change()
        mkt = rets.mean(axis=1)                       # 等权市场日收益
        names = _name_map()

        # 等权市场指数（首日归一 1.0，用于双线图）
        mkt_ret_d = rets.mean(axis=1)
        idx = (1 + mkt_ret_d.fillna(0.0)).cumprod()
        idx = idx / idx.dropna().iloc[0]

        # 全样本逐票回归 -> 按长期 beta 排名
        rows = []
        for sym in close.columns:
            st = _ols_market_model(rets[sym], mkt)
            if st is None:
                continue
            rows.append({
                "symbol": sym, "name": names.get(sym, sym),
                "beta": st["beta"], "alpha": st["alpha"], "corr": st["corr"],
                "r2": st["r2"], "n": st["n"],
                "sys_vol": st["sys_vol"], "idio_vol": st["idio_vol"],
                "tot_vol": st["tot_vol"],
            })
        rows.sort(key=lambda r: (r["beta"] if r["beta"] is not None else -1e9),
                  reverse=True)   # rank 1 = 最高 beta（最激进）
        for i, r in enumerate(rows):
            r["rank"] = i + 1

        betas = [r["beta"] for r in rows if r["beta"] is not None]
        med_beta = sorted(betas)[len(betas) // 2] if betas else None
        index_series = _series_of(idx)

        symbol_info = None
        if symbol and symbol in close.columns:
            st = _ols_market_model(rets[symbol], mkt)
            if st is not None:
                by = {r["symbol"]: r for r in rows}
                rs = rets[symbol]
                # 滚动市场模型（trailing window）
                cov_t = rs.rolling(window_c).cov(mkt)
                var_m_t = mkt.rolling(window_c).var()
                beta_t = cov_t / var_m_t
                alpha_t = rs.rolling(window_c).mean() - beta_t * mkt.rolling(window_c).mean()
                r2_t = rs.rolling(window_c).corr(mkt) ** 2
                sc = close[symbol].dropna()
                sc_norm = sc / sc.iloc[0]
                aligned = pd.concat([rs, mkt], axis=1, keys=["s", "m"]).dropna()
                symbol_info = {
                    "symbol": symbol, "name": names.get(symbol, symbol),
                    "beta": st["beta"], "alpha": st["alpha"], "corr": st["corr"],
                    "r2": st["r2"], "n": st["n"],
                    "var_m": st["var_m"], "var_eps": st["var_eps"],
                    "var_s": st["var_s"],
                    "sys_vol": st["sys_vol"], "idio_vol": st["idio_vol"],
                    "tot_vol": st["tot_vol"],
                    "rs": [float(x) for x in aligned["s"].values],
                    "rm": [float(x) for x in aligned["m"].values],
                    "beta_series": _series_of(beta_t),
                    "alpha_series": _series_of(alpha_t),
                    "r2_series": _series_of(r2_t),
                    "stock_index": _series_of(sc_norm),
                    "rank": by[symbol]["rank"] if symbol in by else None,
                }

        mkt_clean = mkt.dropna()
        mkt_vol = float(mkt_clean.std(ddof=1)) if len(mkt_clean) > 1 else None

        return _clean({
            "symbol": symbol, "window": window_c,
            "n_days": len(close), "n_stocks": len(rows),
            "n_names": int(close.shape[1]),
            "mkt_vol": _clean(mkt_vol),
            "mkt_mean_ret": (_clean(float(mkt_clean.mean())) if len(mkt_clean) else None),
            "median_beta": _clean(med_beta),
            "n_aggressive": sum(1 for b in betas if b >= 1.10),
            "n_defensive": sum(1 for b in betas if b < 0.80),
            "index": index_series, "ranking": rows, "symbol_info": symbol_info,
        })

    return _cached(("beta", symbol, int(window)), build)


# --------------------------------------------------------------------------- #
# 4. 配对协整（pairs_scan / pairs_detail）
# --------------------------------------------------------------------------- #

_MIN_PAIR_OBS = 60          # 配对对齐观测下限
_MIN_PAIR_CORR = 0.30       # 收益相关预筛下限（协整筛选的第一道闸）
_MAX_ADF_PAIRS = 500        # 进入 ADF 回归的配对数上限（按 |corr| 降序截断）


def _adf(spread: pd.Series, min_n: int = _MIN_PAIR_OBS) -> dict | None:
    """增广 Dickey-Fuller（带漂移、滞后 0 阶）检验：Δs_t = c + κ·s_{t-1} + ε。

    纯 pandas 实现（n-1 个观测）。κ < 0 意味着均值回复；ADF t 统计量 = κ̂/SE(κ̂)
    检验单位根（越负越平稳）。AR(1) 速度 φ = 1+κ 给出精确离散半衰期
    hl = -ln2/ln(φ)（0<φ<1 时有效）。
    """
    z = spread.shift(1)
    ds = spread.diff()
    m = pd.concat([ds, z], axis=1, keys=["ds", "z"]).dropna()
    n = len(m)
    if n < min_n:
        return None
    zc, dc = m["z"], m["ds"]
    zbar = float(zc.mean())
    dbar = float(dc.mean())
    szz = float(((zc - zbar) ** 2).sum())
    if szz <= 0:
        return None
    kappa = float(((zc - zbar) * (dc - dbar)).sum() / szz)
    intercept = dbar - kappa * zbar
    resid = dc - (intercept + kappa * zc)
    sse = float((resid ** 2).sum())
    sigma2 = sse / (n - 2) if n > 2 else float("nan")
    se = math.sqrt(sigma2 / szz) if sigma2 > 0 else None
    tstat = (kappa / se) if se and se > 0 else None
    phi = 1.0 + kappa
    halflife = (-math.log(2.0) / math.log(phi)) if 0.0 < phi < 1.0 else None
    return {"kappa": _clean(kappa), "se": _clean(se), "tstat": _clean(tstat),
            "halflife": _clean(halflife), "phi": _clean(phi), "n": int(n)}


def _hedge_spread(va: pd.Series, vb: pd.Series) -> tuple[pd.Series, float, float] | None:
    """价格水平 OLS 对冲（Engle-Granger 第一步）：P_a = α + β·P_b，残差为 spread。"""
    df = pd.concat([va, vb], axis=1, keys=["a", "b"]).dropna()
    if len(df) < _MIN_PAIR_OBS:
        return None
    x, y = df["b"], df["a"]
    var_b = float(x.var(ddof=1))
    if var_b <= 0:
        return None
    beta_v = float(y.cov(x) / var_b)
    alpha_v = float(y.mean() - beta_v * x.mean())
    spread = y - (alpha_v + beta_v * x)
    if float(spread.std(ddof=1)) <= 0:
        return None
    return spread, beta_v, alpha_v


def _ret_corr(va: pd.Series, vb: pd.Series) -> float | None:
    """两票日收益相关（与价格水平协整对照——高相关 ≠ 协整）。"""
    rc = pd.concat([va.pct_change(), vb.pct_change()], axis=1).dropna()
    return float(rc.iloc[:, 0].corr(rc.iloc[:, 1])) if len(rc) > 5 else None


def pairs_scan(top: int = 20) -> dict:
    """全宇宙配对协整性扫描：按 ADF t 统计量升序（最协整在前）返回 top 配对。

    成本控制（两段式，避免全宇宙 O(n²) 次逐对 ADF 回归）：
      1. 预筛——一次性向量化计算全池日收益相关矩阵，只保留 |corr| >= 0.30 的
         候选对（协整几乎必然伴随高收益相关；低相关对的 spread 无交易价值），
         按 |corr| 降序最多取 _MAX_ADF_PAIRS 对进入第二段；
      2. 逐对构造价格水平 OLS 对冲 spread 并做 ADF 回归，按 t 统计量升序排名。
    相关矩阵为单次矩阵运算（毫秒级），真正昂贵的 ADF 只跑在短名单上，
    全程秒级。扫描口径与 pairs_detail 完全一致（同一 _adf / _hedge_spread）。

    返回顶层键：top, n_names, n_pairs_candidates, n_pairs_tested,
    min_corr, max_adf_pairs, pairs。
    每个 pair 行：symbol_a, name_a, symbol_b, name_b, beta, corr,
    tstat, halflife, spread_z, n, rank。
    """
    def build() -> dict:
        empty = {"top": int(top), "n_names": 0, "n_pairs_candidates": 0,
                 "n_pairs_tested": 0, "min_corr": _MIN_PAIR_CORR,
                 "max_adf_pairs": _MAX_ADF_PAIRS, "pairs": []}
        close = close_wide()
        if close.empty or close.shape[1] < 2:
            return _clean(empty)
        names = _name_map()
        rets = close.pct_change()

        # 第一段：向量化收益相关矩阵预筛（单次矩阵运算，规避 O(n²) 逐对开销）
        corr_m = rets.corr(min_periods=_MIN_PAIR_OBS)
        cols = list(close.columns)
        nn = len(cols)
        iu, ju = np.triu_indices(nn, k=1)
        cand = []
        for i, j in zip(iu, ju):
            c = corr_m.iat[i, j]
            if c == c and abs(float(c)) >= _MIN_PAIR_CORR:
                cand.append((abs(float(c)), cols[int(i)], cols[int(j)], float(c)))
        cand.sort(key=lambda t: -t[0])
        shortlist = cand[:_MAX_ADF_PAIRS]

        # 第二段：短名单逐对 ADF
        pairs = []
        for _, sa, sb, corr_v in shortlist:
            hs = _hedge_spread(close[sa], close[sb])
            if hs is None:
                continue
            spread, beta_v, _ = hs
            adf = _adf(spread)
            if not adf or adf["tstat"] is None:
                continue
            sm = float(spread.mean())
            ss = float(spread.std(ddof=1))
            z_now = float((spread.iloc[-1] - sm) / ss) if ss > 0 else None
            pairs.append({
                "symbol_a": sa, "name_a": names.get(sa, sa),
                "symbol_b": sb, "name_b": names.get(sb, sb),
                "beta": _clean(beta_v), "corr": _clean(corr_v),
                "tstat": adf["tstat"], "halflife": adf["halflife"],
                "spread_z": _clean(z_now), "n": adf["n"],
            })
        pairs.sort(key=lambda r: (r["tstat"] if r["tstat"] is not None else 0.0))
        for i, r in enumerate(pairs):
            r["rank"] = i + 1

        return _clean({
            "top": int(top), "n_names": nn,
            "n_pairs_candidates": len(cand), "n_pairs_tested": len(pairs),
            "min_corr": _MIN_PAIR_CORR, "max_adf_pairs": _MAX_ADF_PAIRS,
            "pairs": pairs[:max(1, int(top))],
        })

    return _cached(("pairs_scan", int(top)), build)


def pairs_detail(symbol_a: str, symbol_b: str | None = None) -> dict:
    """指定配对（a, b）的协整细节：对冲 β / ADF / 半衰期 / spread 序列。

    在价格水平上拟合 P_a = α + β·P_b（协整第一步），残差为 spread，再做
    ADF（漂移）回归：κ<0 均值回复，t 统计量检验单位根，φ=1+κ 给出精确
    半衰期 -ln2/ln(φ)。收益相关单独报告（高相关 ≠ 协整的对照）。
    b 缺省时取 a 的最强协整伙伴（即 pairs_scan 的第一名）。

    返回顶层键：a, b, n_days, n_names, pair, partners。
    pair 行：a, b, nameA, nameB, n, beta, alpha, corr, spread_mean,
    spread_std, spread_z, kappa, tstat, halflife, phi, adf_n,
    priceA, priceB, spread_series, zscore_series, raw_pa, raw_pb。
    partners 行与 pairs_scan 的 pair 行同构。
    """
    def build() -> dict:
        empty = {"a": symbol_a, "b": symbol_b, "n_days": 0, "n_names": 0,
                 "pair": None, "partners": []}
        close = close_wide()
        if close.empty or symbol_a not in close.columns:
            return _clean(empty)
        names = _name_map()
        PA = close[symbol_a]
        a = symbol_a

        # a 对全宇宙的伙伴扫描（O(n) 次 ADF——锚定单票的口径）
        partners = []
        for sym in close.columns:
            if sym == a:
                continue
            hs = _hedge_spread(PA, close[sym])
            if hs is None:
                continue
            spread, beta_v, _ = hs
            adf = _adf(spread)
            if not adf or adf["tstat"] is None:
                continue
            sm = float(spread.mean())
            ss = float(spread.std(ddof=1))
            z_now = float((spread.iloc[-1] - sm) / ss) if ss > 0 else None
            corr_v = _ret_corr(PA, close[sym])
            partners.append({
                "symbol": sym, "name": names.get(sym, sym),
                "beta": _clean(beta_v), "corr": _clean(corr_v),
                "tstat": adf["tstat"], "halflife": adf["halflife"],
                "spread_z": _clean(z_now), "n": int(adf["n"]),
            })
        partners.sort(key=lambda r: (r["tstat"] if r["tstat"] is not None else 0.0))
        for i, r in enumerate(partners):
            r["rank"] = i + 1

        # (a, b) 配对细节；b 缺省 -> a 的最强伙伴
        b = symbol_b or (partners[0]["symbol"] if partners else None)
        pair = None
        if b and b in close.columns and b != a:
            hs = _hedge_spread(PA, close[b])
            if hs is not None:
                spread, beta_v, alpha_v = hs
                df_ab = pd.concat([PA, close[b]], axis=1, keys=["a", "b"]).dropna()
                va, vb = df_ab["a"], df_ab["b"]
                sm = float(spread.mean())
                ss = float(spread.std(ddof=1))
                adf = _adf(spread)
                pair = {
                    "a": a, "b": b,
                    "nameA": names.get(a, a), "nameB": names.get(b, b),
                    "n": int(len(spread.dropna())),
                    "beta": _clean(beta_v), "alpha": _clean(alpha_v),
                    "corr": _clean(_ret_corr(PA, close[b])),
                    "spread_mean": _clean(sm), "spread_std": _clean(ss),
                    "spread_z": _clean(float((spread.iloc[-1] - sm) / ss)) if ss > 0 else None,
                    "kappa": adf["kappa"] if adf else None,
                    "tstat": adf["tstat"] if adf else None,
                    "halflife": adf["halflife"] if adf else None,
                    "phi": adf["phi"] if adf else None,
                    "adf_n": adf["n"] if adf else None,
                    "priceA": _series_of(va / va.iloc[0]),
                    "priceB": _series_of(vb / vb.iloc[0]),
                    "spread_series": _series_of(spread),
                    "zscore_series": _series_of((spread - sm) / ss) if ss > 0 else [],
                    "raw_pa": [float(x) for x in va.values],
                    "raw_pb": [float(x) for x in vb.values],
                }

        return _clean({
            "a": a, "b": b, "n_days": len(close),
            "n_names": int(close.shape[1]),
            "pair": pair, "partners": partners,
        })

    return _cached(("pairs_detail", symbol_a, symbol_b), build)


# --------------------------------------------------------------------------- #
# 5. 风险调整收益排名
# --------------------------------------------------------------------------- #

def _risk_adj_stats(prices: pd.Series, min_n: int = 126) -> dict | None:
    """单票风险调整收益统计（全样本）。

    Sharpe  = mean(r)/std(r)·√252（算术，ddof=1，rf=0）
    Sortino = mean(r)/TDD·√252（TDD = sqrt(mean(min(r,0)^2))，MAR=0）
    Calmar  = CAGR / |max drawdown|（CAGR 几何，全样本）
    最大回撤取自价格（=财富）曲线的运行峰值。
    """
    p = prices.dropna()
    if len(p) < min_n:
        return None
    r = p.pct_change().dropna()
    n = len(r)
    if n < 60:
        return None
    mean = float(r.mean())
    std = float(r.std(ddof=1))
    if std <= 0:
        return None
    downside = r.clip(upper=0.0)
    tdd2 = float((downside ** 2).mean())
    tdd = math.sqrt(tdd2) if tdd2 > 0 else None
    cagr = float((p.iloc[-1] / p.iloc[0]) ** (ANN / n) - 1.0)
    dd = p / p.cummax() - 1.0
    max_dd = float(dd.min())
    sharpe = mean / std * SQRT252
    sortino = (mean / tdd * SQRT252) if (tdd and tdd > 0) else None
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else None
    return {
        "ann_ret": _clean(mean * ANN),
        "ann_vol": _clean(std * SQRT252),
        "cagr": _clean(cagr),
        "sharpe": _clean(sharpe),
        "sortino": _clean(sortino),
        "calmar": _clean(calmar),
        "max_dd": _clean(max_dd),
        "n": n,
    }


def risk_adj_ranking(window: int = 126, symbol: str | None = None) -> dict:
    """风险调整收益截面排名（Sharpe / Sortino / Calmar，全样本口径）。

    全宇宙逐票按独立风险调整收益排名：Sharpe = mean/std·√252，
    Sortino = mean/下行偏差·√252，Calmar = CAGR/|max drawdown|；
    按 Sharpe 降序（rank 1 = 单位风险回报最高）。市场基准为等权指数
    （同名口径统计）。指定 symbol 时另附滚动 Sharpe/波动序列与水下曲线
    及原始收益/价格数组。

    返回顶层键：symbol, window, rf, n_days, n_stocks, n_names,
    market, ranking, symbol_info。
    ranking 行：symbol, name, ann_ret, ann_vol, cagr, sharpe, sortino,
    calmar, max_dd, n, rank。
    """
    def build() -> dict:
        empty = {
            "symbol": symbol, "window": window, "rf": 0.0,
            "n_days": 0, "n_stocks": 0, "n_names": 0,
            "market": None, "ranking": [], "symbol_info": None,
        }
        close = close_wide()
        if close.empty:
            return _clean(empty)
        window_c = max(20, min(int(window), len(close) - 1))
        rets = close.pct_change()
        names = _name_map()

        rows = []
        for sym in close.columns:
            st = _risk_adj_stats(close[sym])
            if st is None:
                continue
            rows.append({"symbol": sym, "name": names.get(sym, sym), **st})
        rows.sort(key=lambda r: (r["sharpe"] if r["sharpe"] is not None else -1e9),
                  reverse=True)
        for i, r in enumerate(rows):
            r["rank"] = i + 1

        # 等权市场指数 -> 同口径风险调整统计
        mkt_ret = rets.mean(axis=1)
        mkt_wealth = (1.0 + mkt_ret.fillna(0.0)).cumprod()
        market = _risk_adj_stats(mkt_wealth)

        symbol_info = None
        if symbol and symbol in close.columns:
            st = _risk_adj_stats(close[symbol])
            if st is not None:
                by = {r["symbol"]: r for r in rows}
                p = close[symbol].dropna()
                rs = p.pct_change().dropna()
                mean_t = rs.rolling(window_c).mean()
                std_t = rs.rolling(window_c).std(ddof=1)
                sharpe_t = mean_t / std_t * SQRT252
                vol_t = std_t * SQRT252
                dd_full = p / p.cummax() - 1.0
                symbol_info = {
                    "symbol": symbol, "name": names.get(symbol, symbol),
                    **st,
                    "rank": by[symbol]["rank"] if symbol in by else None,
                    "raw_rets": [float(x) for x in rs.values],
                    "raw_prices": [float(x) for x in p.values],
                    "sharpe_series": _series_of(sharpe_t),
                    "vol_series": _series_of(vol_t),
                    "drawdown_series": _series_of(dd_full),
                }

        return _clean({
            "symbol": symbol, "window": window_c, "rf": 0.0,
            "n_days": len(close), "n_stocks": len(rows),
            "n_names": int(close.shape[1]),
            "market": market, "ranking": rows, "symbol_info": symbol_info,
        })

    return _cached(("risk_adj_ranking", int(window), symbol), build)


# --------------------------------------------------------------------------- #
# 6. 有效下注数
# --------------------------------------------------------------------------- #

def effbets(window: int = 60) -> dict:
    """有效下注数与共同因子集中度（全截面时序）。

    「有效下注数」= 相关矩阵特征谱的参与度 (Σλ)² / Σλ²。相关矩阵迹恰为 N，
    故 Σλ = N、Σλ² = Σ_ij ρ_ij²，得到免特征分解的闭式 eff_bets = N² / Σ_ij ρ_ij²。
    取值 [1, N]：1 = 一个因子驱动一切（完全抱团），N = 全部独立（最大分散）。
    配套序列：rho_bar（精确平均非对角相关）与 sf_ceiling（单因子上限
    N²/(λ1²+(N-1)λr²)，λ1 = 1+(N-1)ρ̄、λr = 1-ρ̄——由凸性，实际值恒 ≤ 上限），
    cluster_ratio = eff_bets / sf_ceiling ∈ (0, 1] 度量单因子世界之外的
    行业/因子聚集。市场已实现波动（等权 RMS）作对照并给出 corr_bets_vol。

    返回顶层键：window, n_days, n_names, eff_bets, eff_bets_pctile,
    rho_bar, rho_pctile, sf_ceiling, cluster_ratio, mkt_vol,
    corr_bets_vol, eff_bets_pcts, eff_bets_series, rho_bar_series,
    sf_ceiling_series, mkt_vol_series。
    """
    def build() -> dict:
        empty = {"window": window, "n_days": 0, "n_names": 0,
                 "eff_bets": None, "eff_bets_pctile": None,
                 "rho_bar": None, "rho_pctile": None,
                 "sf_ceiling": None, "cluster_ratio": None,
                 "mkt_vol": None, "corr_bets_vol": None,
                 "eff_bets_pcts": None,
                 "eff_bets_series": [], "rho_bar_series": [],
                 "sf_ceiling_series": [], "mkt_vol_series": []}
        close = close_wide()
        if close.empty:
            return _clean(empty)
        window_c = max(20, min(int(window), len(close) - 1))
        rets = close.pct_change()
        n = int(close.shape[1])

        eff_idx = rets.index[window_c:]
        eff_vals, rho_vals, sf_vals = [], [], []
        for i in range(window_c, len(rets)):
            sub = rets.iloc[i - window_c:i]
            c = sub.corr().fillna(0.0)
            # 对角强制为 1（自相关恒 1），使矩阵迹恰为 N；常数列自相关
            # 为 NaN（fill 后为 0），逐个加回。
            n_const = int((sub.std(ddof=0) == 0).sum())
            s_all = float(c.sum().sum()) + n_const          # N + Σ_{i≠j} ρ_ij
            s_sq = float((c * c).sum().sum()) + n_const     # Σ_ij ρ_ij² = Σλ²
            eb = (n * n) / s_sq if s_sq > 0 else float("nan")
            rb = (s_all - n) / (n * (n - 1))
            lam1 = 1.0 + (n - 1) * rb
            lamr = 1.0 - rb
            eb_sf = (n * n) / (lam1 * lam1 + (n - 1) * lamr * lamr)
            eff_vals.append(eb)
            rho_vals.append(rb)
            sf_vals.append(eb_sf)

        eff_s = pd.Series(eff_vals, index=eff_idx)
        rho_s = pd.Series(rho_vals, index=eff_idx)
        sf_s = pd.Series(sf_vals, index=eff_idx)
        # 匹配窗口的等权市场已实现波动（RMS 口径）
        mkt_ret = rets.mean(axis=1)
        mkt_vol_s = mkt_ret.rolling(window_c).std() * SQRT252

        valid = eff_s.dropna()
        if valid.empty:
            return _clean(empty)
        last = valid.index[-1]
        eb_last = float(eff_s.loc[last])
        rho_last = float(rho_s.loc[last])
        sf_last = float(sf_s.loc[last])
        eb_pct = float((valid <= eb_last).mean())
        rho_valid = rho_s.dropna()
        rho_pct = (float((rho_valid <= rho_last).mean())
                   if not rho_valid.empty else None)
        cluster_ratio = eb_last / sf_last if sf_last else None
        joint = pd.concat([eff_s, mkt_vol_s], axis=1, keys=["eb", "mv"]).dropna()
        corr_bets_vol = float(joint["eb"].corr(joint["mv"])) if len(joint) > 2 else None
        mkt_vol_last = (float(mkt_vol_s.loc[last])
                        if last in mkt_vol_s.index else None)

        eff_pcts = {
            "p25": _clean(float(valid.quantile(0.25))),
            "p50": _clean(float(valid.quantile(0.50))),
            "p75": _clean(float(valid.quantile(0.75))),
        }

        return _clean({
            "window": window_c, "n_days": len(close), "n_names": n,
            "eff_bets": _clean(eb_last),
            "eff_bets_pctile": _clean(eb_pct),
            "rho_bar": _clean(rho_last),
            "rho_pctile": _clean(rho_pct),
            "sf_ceiling": _clean(sf_last),
            "cluster_ratio": _clean(cluster_ratio),
            "mkt_vol": _clean(mkt_vol_last),
            "corr_bets_vol": _clean(corr_bets_vol),
            "eff_bets_pcts": eff_pcts,
            "eff_bets_series": _series_of(eff_s),
            "rho_bar_series": _series_of(rho_s),
            "sf_ceiling_series": _series_of(sf_s),
            "mkt_vol_series": _series_of(mkt_vol_s),
        })

    return _cached(("effbets", int(window)), build)


# --------------------------------------------------------------------------- #
# 7. 流动性（Amihud）
# --------------------------------------------------------------------------- #

def liquidity(window: int = 60) -> dict:
    """市场非流动性（Amihud）与流动性 regime（时序 + 截面）。

    Amihud (2002) 非流动性：|r_{i,d}| / DVOL_{i,d}（DVOL = volume × close，
    即每港元成交额推动的价格变动 = 往返交易成本代理）。逐票取滚动 window
    均值得平滑冲击序列；市场非流动性 = 截面中位数（对薄票长尾稳健）。
    数值统一 ×1e9 缩放（scale 键），读作「每 10 亿港元成交的收益率冲击」。
    截面部分输出逐票平均非流动性 / 平均成交额 / 年化收益，供最不流动 /
    最流动两张表与非流动性溢价相关（Spearman = 秩的 Pearson）。

    返回顶层键：window, n_days, n_names, market_illiq, market_illiq_pctile,
    corr_illiq_vol, illiq_ret_corr, mkt_vol, scale, illiq_pcts,
    market_illiq_series, mkt_vol_series, most_illiquid, most_liquid。
    截面行：symbol, illiq, dvol, ret, close。
    """
    def build() -> dict:
        empty = {"window": window, "n_days": 0, "n_names": 0,
                 "market_illiq": None, "market_illiq_pctile": None,
                 "corr_illiq_vol": None, "illiq_ret_corr": None,
                 "mkt_vol": None, "scale": None, "illiq_pcts": None,
                 "market_illiq_series": [], "mkt_vol_series": [],
                 "most_illiquid": [], "most_liquid": []}
        close = close_wide()
        if close.empty:
            return _clean(empty)
        window_c = max(20, min(int(window), len(close) - 1))
        SCALE = 1e9
        n = int(close.shape[1])

        # 每日每港元成交额的价格冲击：|收益| / 港元成交额
        dvol = dvol_wide().reindex(index=close.index, columns=close.columns)
        rets = close.pct_change()
        impact = (rets.abs() / dvol).replace(
            [float("inf"), float("-inf")], float("nan"))
        # 逐票滚动均值 Amihud；min_periods < window 容忍少量缺数日
        illiq_name = impact.rolling(window_c, min_periods=window_c // 2).mean()
        # 市场非流动性 = 截面中位数（稳健），缩放
        mkt_illiq = illiq_name.median(axis=1) * SCALE

        # 等权市场已实现波动（nexus 对照）
        mkt_ret = rets.mean(axis=1)
        mkt_vol_s = mkt_ret.rolling(window_c).std() * SQRT252

        valid = mkt_illiq.dropna()
        if valid.empty:
            return _clean(empty)
        last = valid.index[-1]
        illiq_last = float(mkt_illiq.loc[last])
        illiq_pct = float((valid <= illiq_last).mean())
        mkt_vol_last = float(mkt_vol_s.loc[last]) if last in mkt_vol_s.index else None

        joint = pd.concat([mkt_illiq, mkt_vol_s], axis=1, keys=["il", "mv"]).dropna()
        corr_illiq_vol = float(joint["il"].corr(joint["mv"])) if len(joint) > 2 else None

        illiq_pcts = {
            "p25": _clean(float(valid.quantile(0.25))),
            "p50": _clean(float(valid.quantile(0.50))),
            "p75": _clean(float(valid.quantile(0.75))),
        }

        # 截面：逐票平均非流动性 / 成交额 / 年化收益（全历史）
        name_illiq = (illiq_name.mean(axis=0) * SCALE).dropna()
        name_dvol = dvol.mean(axis=0).dropna()
        name_ret = (rets.mean(axis=0) * ANN).dropna()
        last_close = close.iloc[-1]
        common = name_illiq.index.intersection(name_dvol.index) \
            .intersection(name_ret.index).intersection(last_close.dropna().index)
        cs = pd.DataFrame({
            "illiq": name_illiq.reindex(common),
            "dvol": name_dvol.reindex(common),
            "ret": name_ret.reindex(common),
            "close": last_close.reindex(common),
        }).dropna()
        most_illiquid = cs.sort_values("illiq", ascending=False).head(10)
        most_liquid = cs.sort_values("illiq", ascending=True).head(10)
        # Spearman = 秩的 Pearson
        illiq_ret_corr = (float(cs["illiq"].rank().corr(cs["ret"].rank()))
                          if len(cs) > 2 else None)

        def cs_rows(df: pd.DataFrame) -> list[dict]:
            return [{"symbol": str(s),
                     "illiq": _clean(float(df.loc[s, "illiq"])),
                     "dvol": _clean(float(df.loc[s, "dvol"])),
                     "ret": _clean(float(df.loc[s, "ret"])),
                     "close": _clean(float(df.loc[s, "close"]))}
                    for s in df.index]

        return _clean({
            "window": window_c, "n_days": len(close), "n_names": n,
            "market_illiq": _clean(illiq_last),
            "market_illiq_pctile": _clean(illiq_pct),
            "corr_illiq_vol": _clean(corr_illiq_vol),
            "illiq_ret_corr": _clean(illiq_ret_corr),
            "mkt_vol": _clean(mkt_vol_last),
            "scale": SCALE,
            "illiq_pcts": illiq_pcts,
            "market_illiq_series": _series_of(mkt_illiq),
            "mkt_vol_series": _series_of(mkt_vol_s),
            "most_illiquid": cs_rows(most_illiquid),
            "most_liquid": cs_rows(most_liquid),
        })

    return _cached(("liquidity", int(window)), build)
