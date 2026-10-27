"""美股基本面/宏观服务层：宏观叠加、财务轨迹、行业轮动、财报事件研究。

数据一律经 ``app/services/us_analytics_base.py`` 读取：
- aux_frame('us_macro')        宏观日线长表（date, symbol, close, change_pct）
                               ^VIX / ^GSPC / DX-Y.NYB / ^TNX 四条序列
- aux_frame('us_sectors')      行业/风格/宽基 ETF 日线长表（date, symbol, close, volume）
- aux_frame('us_fundamentals') 财务长表（symbol, section, period, metric, value）
                               section ∈ quarterly / earnings_surprise / analyst_estimate
- close_wide() / snapshot_frame()  收盘宽表与名称映射

返回结构与开源参考实现（前端同族页面）的对应 get_* 端点保持一致，
日期一律为 'YYYY-MM-DD' 字符串；numpy/nan 统一清洗为原生类型/None。
macro_overlay 结果按 (宏观文件 mtime, 行情 mtime) 模块级缓存；
trajectory / eventstudy 按票现算，不做缓存。
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .us_analytics_base import aux_frame, close_wide, snapshot_frame

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
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.ndarray, pd.Series)):
        return [_clean(x) for x in v.tolist()]
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if hasattr(v, "item"):
        try:
            return _clean(v.item())
        except Exception:  # noqa: BLE001
            return str(v)
    return v


def _name_map() -> dict[str, str]:
    """symbol → 股票名称（取自最新截面）。"""
    try:
        sn = snapshot_frame()
        if "name" in sn.columns:
            return dict(sn[["symbol", "name"]].drop_duplicates("symbol").itertuples(index=False))
    except Exception:  # noqa: BLE001
        pass
    return {}


# ---------------------------------------------------------------- 宏观叠加

MACRO_LABELS = {
    "^VIX": "VIX 恐慌指数",
    "^GSPC": "S&P 500",
    "DX-Y.NYB": "美元指数",
    "^TNX": "美债10Y收益率",
}
MACRO_KEYS = {"^VIX": "vix", "^GSPC": "spx", "DX-Y.NYB": "dxy", "^TNX": "tnx"}
# β 敏感度表仅覆盖风险三因子：VIX / 标普500 / 美元指数
BETA_KEYS = {"^VIX": "vix", "^GSPC": "spx", "DX-Y.NYB": "dxy"}

_MACRO_CACHE: dict[tuple, Any] = {"key": None, "data": None}


def _macro_regime(key: str, last: float, period_pct: float | None) -> dict:
    """宏观序列当前 regime 标签：VIX 按绝对水位分档，其余按区间涨跌方向。"""
    if key == "vix":
        if last < 15:
            return {"key": "risk_on", "label": "低波动·风险偏好"}
        if last < 20:
            return {"key": "normal", "label": "正常"}
        if last < 30:
            return {"key": "risk_off", "label": "避险·偏紧"}
        return {"key": "crisis", "label": "恐慌"}
    p = period_pct or 0
    if p > 0.005:
        return {"key": "up", "label": "区间上行"}
    if p < -0.005:
        return {"key": "down", "label": "区间下行"}
    return {"key": "flat", "label": "区间走平"}


def macro_overlay(min_days: int = 40) -> dict:
    """宏观叠加视图：4 条宏观序列 + 全池个股对宏观因子的 β 敏感度表。

    序列部分：每条给逐日 close（及日涨跌 chg，%）、区间累计涨跌 period_pct、
    在自身历史中的分位 pctile 与 regime 标签。
    敏感度部分：β = cov(r_stock, r_macro) / var(r_macro)，r 取日收益率
    （macro 的 change_pct 除以 100），仅在两序列共同交易日 ≥ min_days 时输出，
    否则该格为 None。返回 {"series": [...], "sensitivity": {"n_days", "rows"}}。
    """
    ck = _cache_key()
    if _MACRO_CACHE["key"] == ck and _MACRO_CACHE["data"] is not None:
        return _MACRO_CACHE["data"]

    series = _macro_series()
    sens = _macro_sensitivity(min_days=min_days)
    out = {"series": series, "sensitivity": sens}
    _MACRO_CACHE["key"] = ck
    _MACRO_CACHE["data"] = out
    return out


def _cache_key() -> tuple:
    """缓存键：宏观/行业/财务辅助文件与行情文件的 mtime 组合。"""
    from .us_analytics_base import AUX_DIR, HISTORY_PATH
    import os

    parts = []
    for name in ("us_macro", "us_sectors", "us_fundamentals"):
        p = os.path.join(AUX_DIR, f"{name}.parquet")
        try:
            parts.append(os.path.getmtime(p))
        except OSError:
            parts.append(0.0)
    try:
        parts.append(os.path.getmtime(HISTORY_PATH))
    except OSError:
        parts.append(0.0)
    return tuple(parts)


def _macro_series() -> list[dict]:
    """4 条宏观序列：VIX / 标普500 / 美元指数 / 美债10Y。"""
    try:
        m = aux_frame("us_macro").copy()
    except Exception:  # noqa: BLE001
        return []
    m["date"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d")
    out = []
    for msym, key in MACRO_KEYS.items():
        sub = m[m["symbol"] == msym].sort_values("date")
        if sub.empty:
            continue
        closes = pd.to_numeric(sub["close"], errors="coerce").dropna()
        if closes.empty:
            continue
        last = float(closes.iloc[-1])
        first = float(closes.iloc[0])
        period_pct = (last / first - 1) if first else None
        pctile = float((closes < last).mean())
        chg = (
            pd.to_numeric(sub["change_pct"], errors="coerce")
            if "change_pct" in sub.columns
            else pd.Series(np.nan, index=sub.index)
        )
        data = [
            {"time": d, "close": _clean(float(c)),
             "chg": _clean(float(x)) if pd.notna(x) else None}
            for d, c, x in zip(sub["date"], sub["close"], chg)
        ]
        out.append({
            "key": key, "symbol": msym, "label": MACRO_LABELS[msym],
            "data": data, "last": _clean(last),
            "period_pct": _clean(period_pct), "pctile": _clean(pctile),
            "regime": _macro_regime(key, last, period_pct),
        })
    return out


def _macro_sensitivity(min_days: int = 40) -> dict:
    """全池个股对 VIX/标普/美元三因子的日收益 β 表。"""
    rows: list[dict] = []
    try:
        m = aux_frame("us_macro").copy()
    except Exception:  # noqa: BLE001
        return {"n_days": 0, "rows": []}
    m["date"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d")
    mret = m.pivot_table(index="date", columns="symbol", values="change_pct").sort_index() / 100.0
    close = close_wide()
    cret = close.pct_change()
    common = sorted(set(mret.index) & set(cret.index))
    if not common:
        return {"n_days": 0, "rows": []}
    mret = mret.loc[common]
    cret = cret.loc[common]
    names = _name_map()
    for sym in close.columns:
        row: dict[str, Any] = {"symbol": sym, "name": names.get(sym, "")}
        y = cret[sym]
        for msym, key in BETA_KEYS.items():
            if msym not in mret.columns:
                row[f"beta_{key}"] = None
                continue
            x = mret[msym]
            j = x.dropna().index.intersection(y.dropna().index)
            if len(j) < min_days:
                row[f"beta_{key}"] = None
                continue
            xv, yv = x.loc[j], y.loc[j]
            var = float(xv.var())
            row[f"beta_{key}"] = _clean(float(yv.cov(xv) / var)) if var else None
        rows.append(row)
    return {"n_days": len(common), "rows": rows}


# ---------------------------------------------------------------- 行业轮动

SECTOR_LABELS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLI": "工业",
    "XLV": "医疗", "XLP": "必需消费", "XLY": "可选消费", "XLU": "公用事业",
    "XLB": "原材料", "XLRE": "房地产", "XLC": "通信",
    "IWF": "成长", "IWD": "价值", "IWM": "小盘", "SPY": "标普500",
}
SECTOR_CATEGORY = {
    "XLK": "sector", "XLF": "sector", "XLE": "sector", "XLI": "sector",
    "XLV": "sector", "XLP": "sector", "XLY": "sector", "XLU": "sector",
    "XLB": "sector", "XLRE": "sector", "XLC": "sector",
    "IWF": "style", "IWD": "style", "IWM": "style", "SPY": "index",
}
SECTOR_HORIZONS = (1, 5, 20, 60)


def rotation() -> list[dict]:
    """行业/风格/宽基 ETF 轮动基础数据：逐只日收盘序列 + 多区间收益。

    每项 {symbol, label, category, data:[{time, close}], last,
    ret_1d/5d/20d/60d, ret_period}。区间收益 = 最新收盘 / h 日前收盘 − 1；
    ret_period = 全样本首尾收益。排名/轮动矩阵/相对强弱由前端计算。
    """
    try:
        m = aux_frame("us_sectors").copy()
    except Exception:  # noqa: BLE001
        return []
    m["date"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d")
    out = []
    for sym in SECTOR_LABELS:
        sub = m[m["symbol"] == sym].sort_values("date")
        if sub.empty:
            continue
        closes = pd.to_numeric(sub["close"], errors="coerce")
        data = [
            {"time": d, "close": _clean(float(c))}
            for d, c in zip(sub["date"], closes) if pd.notna(c)
        ]
        cdrop = closes.dropna()
        if len(cdrop) < 2:
            continue
        last = float(cdrop.iloc[-1])
        rets: dict[str, Any] = {}
        for h in SECTOR_HORIZONS:
            rets[f"ret_{h}d"] = (
                _clean(last / float(cdrop.iloc[-1 - h]) - 1) if len(cdrop) > h else None
            )
        rets["ret_period"] = _clean(last / float(cdrop.iloc[0]) - 1)
        out.append({
            "symbol": sym, "label": SECTOR_LABELS[sym],
            "category": SECTOR_CATEGORY[sym],
            "data": data, "last": _clean(last), **rets,
        })
    return out


# ---------------------------------------------------------------- 财务轨迹

_FUND_NOTE = (
    "财务长表 quarterly 段仅覆盖各公司近若干财季，且 period 是各公司自有的"
    "财季期末日（非统一历法季度）。本视图呈现逐季轨迹与最新季截面排名，"
    "不声称长历史时序深度；YoY 仅在存在上年同期值时可算。"
)

QUARTERLY_METRICS = ["total_revenue", "net_income", "diluted_eps",
                     "gross_profit", "operating_income"]


def _fund_quarterly() -> pd.DataFrame:
    """quarterly 段长表 → 宽表（symbol × period 为行，metric 为列），mtime 缓存。"""
    f = aux_frame("us_fundamentals")
    q = f[f["section"] == "quarterly"][["symbol", "period", "metric", "value"]]
    w = q.pivot_table(index=["symbol", "period"], columns="metric", values="value").reset_index()
    w["period"] = pd.to_datetime(w["period"], errors="coerce")
    w = w[w["period"].notna()].sort_values(["symbol", "period"]).reset_index(drop=True)
    return w


def _yoy(s: pd.Series) -> pd.Series:
    """同比：metric[p] / metric[p−1 年] − 1（上年同期按日历匹配）。"""
    prior = s.reindex(s.index - pd.DateOffset(years=1)).values
    with np.errstate(divide="ignore", invalid="ignore"):
        return pd.Series(s.values / prior - 1.0, index=s.index)


def _qoq(s: pd.Series) -> pd.Series:
    """环比：metric[p] / metric[p−1 财季] − 1。"""
    with np.errstate(divide="ignore", invalid="ignore"):
        return pd.Series(s.values / s.shift(1).values - 1.0, index=s.index)


def trajectory(symbol: str | None = None) -> dict:
    """逐季财务轨迹 + 最新财季截面分位。

    - symbol=None：返回全池最新财季截面（ranking，按最新季营收 YoY 降序排名）
      与市场分位（market：rev_yoy / gross_margin / net_margin 的 25/50/75 分位）。
    - symbol=票：额外返回 symbol_info——该票逐季指标序列、派生利润率
      （毛利/营业/净利率 = 对应利润 / 营收）与 YoY/QoQ 增长序列。
    结构与参考页面一致：n_stocks / quarter_depth / period_span /
    data_window_note / ranking / symbol_info / market。
    """
    w = _fund_quarterly()
    names = _name_map()

    def _slist(s: pd.Series) -> list[dict]:
        return [{"time": p.strftime("%Y-%m-%d"), "value": _clean(float(v))}
                for p, v in s.items()]

    def _per_symbol(sub_i: pd.DataFrame, sym: str, name: str):
        rev = sub_i["total_revenue"]
        eps = sub_i["diluted_eps"]
        gp, op, ni = sub_i["gross_profit"], sub_i["operating_income"], sub_i["net_income"]
        with np.errstate(divide="ignore", invalid="ignore"):
            gm = (gp / rev).where(~rev.eq(0))
            om = (op / rev).where(~rev.eq(0))
            nm = (ni / rev).where(~rev.eq(0))
        rev_yoy, rev_qoq = _yoy(rev), _qoq(rev)
        eps_yoy, eps_qoq = _yoy(eps), _qoq(eps)

        def L(s: pd.Series):
            v = s.iloc[-1]
            return _clean(float(v))

        latest = {
            "symbol": sym, "name": name,
            "latest_period": sub_i.index[-1].strftime("%Y-%m-%d"),
            "n_quarters": int(len(sub_i)),
            "revenue": L(rev), "rev_yoy": L(rev_yoy), "rev_qoq": L(rev_qoq),
            "gross_margin": L(gm), "operating_margin": L(om), "net_margin": L(nm),
            "diluted_eps": L(eps), "eps_yoy": L(eps_yoy),
        }
        series = {
            "periods": [p.strftime("%Y-%m-%d") for p in sub_i.index],
            "metrics": {
                "total_revenue": _slist(rev), "net_income": _slist(ni),
                "diluted_eps": _slist(eps), "gross_profit": _slist(gp),
                "operating_income": _slist(op),
            },
            "margins": {"gross": _slist(gm), "operating": _slist(om), "net": _slist(nm)},
            "growth": {"rev_qoq": _slist(rev_qoq), "rev_yoy": _slist(rev_yoy),
                       "eps_qoq": _slist(eps_qoq), "eps_yoy": _slist(eps_yoy)},
        }
        return latest, series

    ranking: list[dict] = []
    by_sym: dict[str, dict] = {}
    for sym, sub in w.groupby("symbol"):
        sub_i = sub.set_index("period").sort_index()
        latest, series = _per_symbol(sub_i, sym, names.get(sym, sym))
        ranking.append(latest)
        by_sym[sym] = series

    ranking.sort(key=lambda r: (r["rev_yoy"] is not None,
                                r["rev_yoy"] if r["rev_yoy"] is not None else float("-inf")),
                 reverse=True)
    for i, r in enumerate(ranking):
        r["rank"] = i + 1

    symbol_info = None
    if symbol and symbol in by_sym:
        rk = next((r for r in ranking if r["symbol"] == symbol), None)
        symbol_info = {
            "symbol": symbol, "name": names.get(symbol, symbol),
            **by_sym[symbol], "latest": rk,
        }

    def _pct(arr: list, q: float):
        s = pd.Series([x for x in arr if x is not None], dtype=float)
        return None if s.empty else _clean(float(s.quantile(q)))

    nq = pd.Series([r["n_quarters"] for r in ranking], dtype=float)
    market = {
        m: {str(q): _pct([r[m] for r in ranking], q) for q in (0.25, 0.5, 0.75)}
        for m in ("rev_yoy", "gross_margin", "net_margin")
    }
    span_min = w["period"].min().strftime("%Y-%m-%d") if len(w) else None
    span_max = w["period"].max().strftime("%Y-%m-%d") if len(w) else None
    return {
        "n_stocks": len(ranking),
        "quarter_depth": {
            "min": int(nq.min()) if len(nq) else 0,
            "med": int(nq.median()) if len(nq) else 0,
            "max": int(nq.max()) if len(nq) else 0,
        },
        "period_span": f"{span_min} → {span_max}" if span_min else "",
        "data_window_note": _FUND_NOTE,
        "ranking": ranking,
        "symbol_info": symbol_info,
        "market": market,
    }


# ---------------------------------------------------------------- 财报事件研究

def _fund_earnings_events() -> pd.DataFrame:
    """earnings_surprise 段 → 宽表（symbol × 公告日，含 estimate/reported/surprise_pct）。

    period 在该段内是**财报实际公告日**（非财季期末），非日期解析失败的行丢弃；
    analyst_estimate 段用 '+1q' 之类相对编码，不在此读取。
    """
    f = aux_frame("us_fundamentals")
    e = f[f["section"] == "earnings_surprise"][["symbol", "period", "metric", "value"]]
    w = e.pivot_table(index=["symbol", "period"], columns="metric", values="value").reset_index()
    w = w.rename(columns={"period": "date"})
    w["date"] = pd.to_datetime(w["date"], errors="coerce")
    w = w[w["date"].notna()].sort_values(["symbol", "date"]).reset_index(drop=True)
    return w


def _car_from_ar(ar: list, a: int, b: int, pre: int):
    """CAR[a,b] = 事件日偏移 a..b 的 AR 求和（None 跳过）。"""
    lo, hi = a + pre, b + pre
    seg = [x for x in ar[lo:hi + 1] if x is not None]
    return _clean(float(sum(seg))) if seg else None


def _car_from_caar(caar: list, a: int, b: int, pre: int):
    """CAR[a,b] = CAAR[b] − CAAR[a−1]（对累计序列做望远镜差分）。"""
    hi = caar[b + pre] if 0 <= b + pre < len(caar) else None
    lo = caar[a - 1 + pre] if 0 <= a - 1 + pre < len(caar) else None
    if hi is None or lo is None:
        return None
    return _clean(float(hi - lo))


def eventstudy(symbol: str | None = None, pre: int = 10, post: int = 30) -> dict:
    """财报公告日事件研究：事件时序异常收益 AR/AAR/CAAR + 财报后漂移（PEAD）。

    口径：以 earnings_surprise 段的公告日为事件，t=0 = 公告日后首个交易日
    （含当日）；AR 用市场调整模型 AR_t = r_stock,t − r_mkt,t，市场为全池
    等权日收益均值。按 surprise 符号分桶（beat>0 / miss<0 / unknown），
    聚合出 [-pre, +post] 的 AAR 与累计 CAAR，CAR 取 reaction([-1,+1]) 与
    drift([+1,+post]) 两窗。
    symbol 给定时：聚合仅统计该票事件（其 symbol_info 同口径）；symbol=None
    时为全池事件。样本不足/窗口越界的剔除计数见 n_excluded_* 各键。
    """
    offsets = list(range(-pre, post + 1))
    empty = {
        "symbol": symbol, "pre": pre, "post": post, "offsets": offsets,
        "trading_days": [], "total_events": 0, "n_all": 0, "n_beat": 0,
        "n_miss": 0, "n_unk": 0, "n_excluded_window": 0,
        "n_excluded_nosym": 0, "n_excluded_outside": 0, "n_symbols": 0,
        "date_min": None, "date_max": None,
        "aar_all": [], "caar_all": [], "aar_beat": [], "caar_beat": [],
        "aar_miss": [], "caar_miss": [], "n_per_offset": [],
        "car": {"all": {"reaction": None, "drift": None},
                "beat": {"reaction": None, "drift": None},
                "miss": {"reaction": None, "drift": None}},
        "events": [], "symbol_info": None,
    }

    try:
        ev = _fund_earnings_events()
    except Exception:  # noqa: BLE001
        return empty
    if ev.empty:
        return empty
    total_events = int(len(ev))

    close = close_wide()
    if close.empty:
        return empty
    rets = close.pct_change()
    mkt = rets.mean(axis=1)
    trading_days = pd.DatetimeIndex(pd.to_datetime(close.index))
    n_td = len(trading_days)
    first_day, last_day = trading_days[0], trading_days[-1]
    cols = set(close.columns)
    names = _name_map()

    ar_all: list[list] = [[] for _ in offsets]
    ar_beat: list[list] = [[] for _ in offsets]
    ar_miss: list[list] = [[] for _ in offsets]
    ar_unk: list[list] = [[] for _ in offsets]

    events_out: list[dict] = []
    sym_events: list[dict] = []
    n_beat = n_miss = n_unk = 0
    n_ex_window = n_ex_nosym = n_ex_outside = 0
    included_dates: list[pd.Timestamp] = []
    included_syms: set[str] = set()

    for row in ev.itertuples(index=False):
        sym = row.symbol
        edate = row.date
        sp = getattr(row, "surprise_pct", None)
        spv = float(sp) if sp == sp and sp is not None else None
        if symbol is not None and sym != symbol:
            continue
        if sym not in cols:
            n_ex_nosym += 1
            continue
        if edate < first_day or edate > last_day:
            n_ex_outside += 1
            continue
        t0_idx = int(trading_days.searchsorted(edate, side="left"))
        if t0_idx - pre < 0 or t0_idx + post >= n_td:
            n_ex_window += 1
            continue

        lo, hi = t0_idx - pre, t0_idx + post
        rvec = rets[sym].iloc[lo:hi + 1].tolist()
        mvec = mkt.iloc[lo:hi + 1].tolist()
        rwin = [_clean(float(v)) for v in rvec]
        mwin = [_clean(float(v)) for v in mvec]
        ar = [_clean(float(rv - mv)) if (rv == rv and mv == mv) else None
              for rv, mv in zip(rvec, mvec)]

        if spv is None:
            bucket, col = "unk", ar_unk
            n_unk += 1
        elif spv > 0:
            bucket, col = "beat", ar_beat
            n_beat += 1
        else:
            bucket, col = "miss", ar_miss
            n_miss += 1
        for i, a in enumerate(ar):
            ar_all[i].append(a)
            col[i].append(a)

        t0 = trading_days[t0_idx]
        reaction = _car_from_ar(ar, -1, 1, pre)
        drift = _car_from_ar(ar, 1, post, pre)
        events_out.append({
            "symbol": sym, "date": edate.strftime("%Y-%m-%d"),
            "t0": t0.strftime("%Y-%m-%d"),
            "surprise_pct": _clean(spv), "car_reaction": reaction,
            "car_drift": drift, "rets_win": rwin, "mkt_win": mwin,
        })
        included_dates.append(edate)
        included_syms.add(sym)
        if symbol and sym == symbol:
            est = getattr(row, "estimate", None)
            rep = getattr(row, "reported", None)
            sym_events.append({
                "date": edate.strftime("%Y-%m-%d"), "t0": t0.strftime("%Y-%m-%d"),
                "surprise_pct": _clean(spv),
                "estimate": _clean(float(est) if est == est and est is not None else None),
                "reported": _clean(float(rep) if rep == rep and rep is not None else None),
                "car_reaction": reaction, "car_drift": drift,
            })

    n_all = len(events_out)
    if n_all == 0:
        return {**empty, "total_events": total_events,
                "n_excluded_window": n_ex_window, "n_excluded_nosym": n_ex_nosym,
                "n_excluded_outside": n_ex_outside}

    def aar_caar(buckets: list[list[list]]) -> tuple[list, list, list]:
        aar, n_per = [], []
        for col in buckets:
            finite = [x for x in col if x is not None]
            aar.append(_clean(float(sum(finite) / len(finite))) if finite else None)
            n_per.append(len(finite))
        caar, run = [], 0.0
        for v in aar:
            run += v if v is not None else 0.0
            caar.append(_clean(run))
        return aar, caar, n_per

    aar_all, caar_all, n_per_offset = aar_caar(ar_all)
    aar_beat, caar_beat, _ = aar_caar(ar_beat)
    aar_miss, caar_miss, _ = aar_caar(ar_miss)

    symbol_info = None
    if symbol and symbol in included_syms:
        symbol_info = {
            "symbol": symbol, "name": names.get(symbol, symbol),
            "n_events": len(sym_events), "events": sym_events,
        }

    return {
        "symbol": symbol, "pre": pre, "post": post, "offsets": offsets,
        "trading_days": [d.strftime("%Y-%m-%d") for d in trading_days],
        "total_events": total_events,
        "n_all": n_all, "n_beat": n_beat, "n_miss": n_miss, "n_unk": n_unk,
        "n_excluded_window": n_ex_window, "n_excluded_nosym": n_ex_nosym,
        "n_excluded_outside": n_ex_outside, "n_symbols": len(included_syms),
        "date_min": min(included_dates).strftime("%Y-%m-%d"),
        "date_max": max(included_dates).strftime("%Y-%m-%d"),
        "aar_all": aar_all, "caar_all": caar_all,
        "aar_beat": aar_beat, "caar_beat": caar_beat,
        "aar_miss": aar_miss, "caar_miss": caar_miss,
        "n_per_offset": n_per_offset,
        "car": {
            "all": {"reaction": _car_from_caar(caar_all, -1, 1, pre),
                    "drift": _car_from_caar(caar_all, 1, post, pre)},
            "beat": {"reaction": _car_from_caar(caar_beat, -1, 1, pre),
                     "drift": _car_from_caar(caar_beat, 1, post, pre)},
            "miss": {"reaction": _car_from_caar(caar_miss, -1, 1, pre),
                     "drift": _car_from_caar(caar_miss, 1, post, pre)},
        },
        "events": events_out,
        "symbol_info": symbol_info,
    }
