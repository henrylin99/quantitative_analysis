"""数据洞察服务：估值分位 / 资金流深历史 / 财务同业对比 / 组合相关性 / 历史日内统计 / 事件复盘。

数据边界（截至 2026-10）：
- daily_basic 2024-01 起（估值分位窗口即全历史）
- moneyflow 2025-10 起（资金流结论按 ~1 年窗口解读）
- stock_minute 2026-04 起（日内统计窗口 ~6 个月）
- event_archive 2026-10 起（事件复盘随归档积累）
"""
import glob
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader
from app.utils.cache import cached

_data_reader = ParquetDataReader()

EVENT_ARCHIVE_TYPES = ["limit_up", "limit_down", "limit_break", "ladder", "dragon_tiger", "mood"]
EVENT_ARCHIVE_LABELS = {
    "limit_up": "涨停池",
    "limit_down": "跌停池",
    "limit_break": "炸板池",
    "ladder": "连板天梯",
    "dragon_tiger": "龙虎榜",
    "mood": "市场情绪",
}


def _sanitize_records(df: pd.DataFrame, limit: Optional[int] = None) -> List[dict]:
    if df is None or df.empty:
        return []
    if limit:
        df = df.head(limit)
    df = df.where(df.notna(), None)
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in list(r.items()):
            if isinstance(v, (np.generic,)):
                r[k] = v.item()
            elif isinstance(v, (pd.Timestamp,)):
                r[k] = v.strftime("%Y-%m-%d %H:%M:%S") if v.time() != pd.Timestamp("2000-01-01").time() else v.strftime("%Y-%m-%d")
    return records


def _names_map(ts_codes: List[str]) -> Dict[str, str]:
    if not ts_codes:
        return {}
    basic = _data_reader.get_stock_basic()
    sub = basic[basic["ts_code"].isin(set(ts_codes))]
    return dict(zip(sub["ts_code"], sub["name"]))


def _pct_rank(series: pd.Series, value: float) -> Optional[float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0 or value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return float((s <= value).mean() * 100)


# ---------------------------------------------------------------------------
# 1. 估值分位
# ---------------------------------------------------------------------------

def valuation_history(ts_code: str) -> dict:
    """单票估值历史 + 当前值全历史分位。"""
    basic = _data_reader.get_daily_basic(ts_codes=[ts_code])
    daily = _data_reader.get_daily(ts_codes=[ts_code])
    if basic.empty:
        return {"error": "无 daily_basic 数据"}

    basic = basic.sort_values("trade_date")
    merged = basic
    if not daily.empty:
        px = daily[["trade_date", "close"]].rename(columns={"close": "price"})
        merged = basic.merge(px, on="trade_date", how="left")

    merged["date"] = merged["trade_date"].dt.strftime("%Y-%m-%d")

    def _field_pct(col: str) -> Optional[float]:
        vals = merged[col].dropna()
        return _pct_rank(vals, float(vals.iloc[-1])) if len(vals) else None

    latest = merged.iloc[-1]
    percentiles = {c: _field_pct(c) for c in ["pe_ttm", "pb", "dv_ttm", "turnover_rate"]}
    current = {c: (None if pd.isna(latest.get(c)) else float(latest.get(c))) for c in ["pe_ttm", "pb", "dv_ttm", "turnover_rate"]}

    series = {
        c: [
            {"date": r["date"], "value": (None if pd.isna(r[c]) else float(r[c]))}
            for _, r in merged.iterrows()
        ]
        for c in ["pe_ttm", "pb", "dv_ttm", "turnover_rate"]
    }
    prices = [
        {"date": r["date"], "value": (None if pd.isna(r.get("price")) else float(r.get("price")))}
        for _, r in merged.iterrows()
    ]
    return {
        "ts_code": ts_code,
        "name": _names_map([ts_code]).get(ts_code),
        "start_date": merged["date"].iloc[0],
        "end_date": merged["date"].iloc[-1],
        "current": current,
        "percentiles": percentiles,
        "series": series,
        "prices": prices,
    }


@cached(expire=3600, key_prefix='insights_thermo')
def valuation_thermometer() -> dict:
    """市场估值温度计：全市场 pe_ttm/pb 中位数逐日序列 + 扩张分位，叠加上证指数。"""
    base = os.path.join(_data_reader.data_dir, "daily_basic", "daily")
    files = sorted(glob.glob(os.path.join(base, "**", "data.parquet"), recursive=True))
    if not files:
        return {"error": "无 daily_basic 数据"}

    frames = []
    for f in files:
        try:
            df = pd.read_parquet(f, columns=["trade_date", "pe_ttm", "pb"])
            if not df.empty:
                frames.append(df)
        except Exception as e:
            logger.warning(f"读取 {f} 失败: {e}")
    if not frames:
        return {"error": "无 daily_basic 数据"}

    df = pd.concat(frames, ignore_index=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce", format="mixed")
    df = df.dropna(subset=["trade_date"])

    def _median_positive(g: pd.DataFrame, col: str) -> float:
        v = pd.to_numeric(g[col], errors="coerce")
        v = v[(v > 0) & v.notna()]
        return float(v.median()) if len(v) else np.nan

    agg = df.groupby("trade_date").apply(lambda g: pd.Series({
        "pe": _median_positive(g, "pe_ttm"),
        "pb": _median_positive(g, "pb"),
        "count": int(g["pe_ttm"].notna().sum()),
    })).reset_index().sort_values("trade_date")

    for col in ["pe", "pb"]:
        expanding_rank = agg[col].expanding().apply(
            lambda x: (np.nansum(x[:-1] <= x[-1]) / max(1, np.sum(~np.isnan(x[:-1])))) * 100,
            raw=True,
        )
        agg[f"{col}_pct"] = expanding_rank.round(1)

    idx = _data_reader.get_index_daily(ts_codes=["000001.SH"]) if hasattr(_data_reader, "get_index_daily") else pd.DataFrame()
    idx_series = []
    if not idx.empty:
        idx = idx.sort_values("trade_date")
        for _, r in idx.iterrows():
            d = r["trade_date"]
            d = pd.to_datetime(d) if not isinstance(d, pd.Timestamp) else d
            idx_series.append({"date": d.strftime("%Y-%m-%d"), "value": float(r["close"]) if pd.notna(r["close"]) else None})

    thermo = [
        {
            "date": r["trade_date"].strftime("%Y-%m-%d"),
            "pe": None if pd.isna(r["pe"]) else round(float(r["pe"]), 2),
            "pb": None if pd.isna(r["pb"]) else round(float(r["pb"]), 2),
            "pe_pct": None if pd.isna(r.get("pe_pct")) else float(r["pe_pct"]),
            "pb_pct": None if pd.isna(r.get("pb_pct")) else float(r["pb_pct"]),
        }
        for _, r in agg.iterrows()
    ]
    latest = agg.iloc[-1]
    return {
        "series": thermo,
        "index_series": idx_series,
        "index_code": "000001.SH",
        "latest": {
            "date": latest["trade_date"].strftime("%Y-%m-%d"),
            "pe": None if pd.isna(latest["pe"]) else round(float(latest["pe"]), 2),
            "pb": None if pd.isna(latest["pb"]) else round(float(latest["pb"]), 2),
            "pe_pct": None if pd.isna(latest.get("pe_pct")) else float(latest.get("pe_pct")),
        },
    }


# ---------------------------------------------------------------------------
# 2. 资金流深历史
# ---------------------------------------------------------------------------

def _moneyflow_window(days: int) -> pd.DataFrame:
    end = pd.Timestamp.today()
    start = (end - pd.Timedelta(days=int(days) * 2 + 10)).strftime("%Y%m%d")
    return _data_reader.get_moneyflow(start_date=start)


@cached(expire=1800, key_prefix='insights_mf_streaks')
def moneyflow_streaks(days: int = 20, min_streak: int = 3, top: int = 20) -> dict:
    """连续净流入排行：从最新交易日往前连续 net_mf_amount > 0 的天数与累计金额。"""
    mf = _moneyflow_window(days)
    if mf.empty:
        return {"error": "无资金流数据"}
    mf = mf.sort_values("trade_date")
    last_date = mf["trade_date"].max()
    dates = sorted(mf["trade_date"].unique())[-int(days):]
    mf = mf[mf["trade_date"].isin(dates)]
    codes = mf["ts_code"].unique().tolist()
    daily_px = _data_reader.get_daily(ts_codes=codes, start_date=dates[0].strftime("%Y%m%d"))
    px_map = daily_px.sort_values("trade_date").groupby("ts_code")["close"].last().to_dict() if not daily_px.empty else {}

    pos = mf[mf["net_mf_amount"] > 0]
    streaks = []
    for code, g in pos.groupby("ts_code"):
        g = g.sort_values("trade_date")
        streak = 0
        for d in reversed(dates):
            if d in set(g["trade_date"]):
                streak += 1
            else:
                break
        if streak >= min_streak:
            cum_days = dates[-streak:]
            cum_amt = float(mf[(mf["ts_code"] == code) & (mf["trade_date"].isin(cum_days))]["net_mf_amount"].sum())
            streaks.append({"ts_code": code, "streak": streak, "cum_amount": round(cum_amt, 1), "close": px_map.get(code)})
    streaks.sort(key=lambda x: (x["streak"], x["cum_amount"]), reverse=True)
    streaks = streaks[: int(top)]
    names = _names_map([s["ts_code"] for s in streaks])
    for s in streaks:
        s["name"] = names.get(s["ts_code"])
    return {"end_date": last_date.strftime("%Y-%m-%d"), "window_days": int(days), "stocks": streaks}


@cached(expire=1800, key_prefix='insights_mf_div')
def moneyflow_divergence(days: int = 20, top: int = 20) -> dict:
    """量价背离：区间价格下跌但主力资金累计净流入为正。"""
    mf = _moneyflow_window(days)
    if mf.empty:
        return {"error": "无资金流数据"}
    mf = mf.sort_values("trade_date")
    dates = sorted(mf["trade_date"].unique())[-int(days):]
    mf = mf[mf["trade_date"].isin(dates)]
    codes = mf["ts_code"].unique().tolist()

    daily = _data_reader.get_daily(ts_codes=codes, start_date=dates[0].strftime("%Y%m%d"))
    if daily.empty:
        return {"error": "无行情数据"}
    daily = daily.sort_values("trade_date")
    px_first = daily.groupby("ts_code")["close"].first()
    px_last = daily.groupby("ts_code")["close"].last()

    cum = mf.groupby("ts_code")["net_mf_amount"].sum()
    df = pd.DataFrame({"pct": (px_last / px_first - 1) * 100, "cum_net": cum}).dropna()
    df = df[(df["pct"] < 0) & (df["cum_net"] > 0)].sort_values("cum_net", ascending=False).head(int(top))
    names = _names_map(df.index.tolist())
    stocks = [
        {
            "ts_code": code,
            "name": names.get(code),
            "pct": round(float(r["pct"]), 2),
            "cum_net": round(float(r["cum_net"]), 1),
            "close": float(px_last.get(code)) if pd.notna(px_last.get(code)) else None,
        }
        for code, r in df.iterrows()
    ]
    return {"end_date": dates[-1].strftime("%Y-%m-%d"), "window_days": int(days), "stocks": stocks}


# ---------------------------------------------------------------------------
# 3. 财务同业对比
# ---------------------------------------------------------------------------

@cached(expire=3600, key_prefix='insights_peer')
def peer_compare(ts_code: str, top_peers: int = 15) -> dict:
    """同行业横向对比：最新年报核心指标 + 目标股票多年趋势。"""
    basic = _data_reader.get_stock_basic(ts_code=ts_code)
    if basic.empty:
        return {"error": "未知股票"}
    industry = basic.iloc[0].get("industry")

    pool = _data_reader.get_stock_basic()
    peers = pool[(pool["industry"] == industry) & (pool.get("list_status", "L") == "L")]["ts_code"].tolist()
    if ts_code not in peers:
        peers.append(ts_code)

    # 行业大时按最新市值截断，控制三表读取量
    db = _data_reader.get_daily_basic(ts_codes=peers)
    if not db.empty:
        last = db["trade_date"].max()
        mv = db[db["trade_date"] == last].groupby("ts_code")["total_mv"].last().fillna(0)
        ranked = mv.sort_values(ascending=False).index.tolist()
        keep = ranked[: int(top_peers)]
        if ts_code not in keep:
            keep = keep[: int(top_peers) - 1] + [ts_code]
        peers = keep

    income = _data_reader.get_income_statement(peers)
    balance = _data_reader.get_balance_sheet(peers)
    cash = _data_reader.get_cash_flow(peers)

    def _annual(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "end_date" not in df.columns:
            return pd.DataFrame()
        df = df.copy()
        df["end_date"] = df["end_date"].astype(str)
        return df[df["end_date"].str.endswith("1231")]

    inc_a, bal_a, cash_a = _annual(income), _annual(balance), _annual(cash)
    latest_year = max(
        [inc_a["end_date"].max() if not inc_a.empty else "",
         bal_a["end_date"].max() if not bal_a.empty else ""]
    )
    if not latest_year:
        return {"error": "无年报数据", "industry": industry}

    def _year_rows(df: pd.DataFrame, year: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        rows = df[df["end_date"] == year].copy()
        if rows.empty:
            return pd.DataFrame()
        # 同一年报可能存在快报/修订多行，按披露日取最新一条
        if "ann_date" in rows.columns:
            rows["ann_date"] = rows["ann_date"].astype(str)
            rows = rows.sort_values(["ts_code", "ann_date"], kind="mergesort")
        return rows.groupby("ts_code").last().reset_index()

    inc_y = _year_rows(inc_a, latest_year)
    inc_prev = _year_rows(inc_a, str(int(latest_year[:4]) - 1) + "1231")
    bal_y = _year_rows(bal_a, latest_year)
    cash_y = _year_rows(cash_a, latest_year)

    merged = inc_y[["ts_code", "total_revenue", "revenue", "n_income"]].copy()
    for src, cols in [
        (bal_y, ["total_assets", "total_liab", "total_hldr_eqy_inc_min_int", "total_hldr_eqy_exc_min_int"]),
        (cash_y, ["n_cashflow_act"]),
    ]:
        if not src.empty:
            merged = merged.merge(src[["ts_code"] + cols], on="ts_code", how="left")
    if not inc_prev.empty:
        prev = inc_prev[["ts_code", "total_revenue", "revenue", "n_income"]].rename(
            columns={"total_revenue": "tr_prev", "revenue": "rev2_prev", "n_income": "ni_prev"})
        merged = merged.merge(prev, on="ts_code", how="left")

    # 字段回退：银行股及部分年报 total_revenue 缺失，用营业收入兜底；
    # 权益优先含少数股东口径，缺失退到不含少数股东口径
    merged["rev"] = merged["total_revenue"].combine_first(merged["revenue"])
    merged["rev_prev"] = merged["tr_prev"].combine_first(merged["rev2_prev"])
    if "total_hldr_eqy_inc_min_int" not in merged.columns:
        merged["total_hldr_eqy_inc_min_int"] = np.nan
    if "total_hldr_eqy_exc_min_int" not in merged.columns:
        merged["total_hldr_eqy_exc_min_int"] = np.nan
    merged["equity"] = merged["total_hldr_eqy_inc_min_int"].combine_first(merged["total_hldr_eqy_exc_min_int"])

    def _ratio(num, den):
        with np.errstate(divide="ignore", invalid="ignore"):
            r = num / den
        return r.replace([np.inf, -np.inf], np.nan)

    merged["rev_yoy"] = ((_ratio(merged["rev"], merged["rev_prev"]) - 1) * 100).round(1)
    merged["ni_yoy"] = ((_ratio(merged["n_income"], merged["ni_prev"]) - 1) * 100).round(1)
    merged["net_margin"] = (_ratio(merged["n_income"], merged["rev"]) * 100).round(1)
    merged["roe"] = (_ratio(merged["n_income"], merged["equity"]) * 100).round(1)
    merged["debt_ratio"] = (_ratio(merged["total_liab"], merged["total_assets"]) * 100).round(1)
    merged["ocf_ni"] = _ratio(merged["n_cashflow_act"], merged["n_income"]).round(2)

    merged = merged.sort_values("rev", ascending=False)
    names = _names_map(merged["ts_code"].tolist())
    table = [
        {
            "ts_code": r["ts_code"],
            "name": names.get(r["ts_code"]),
            "is_target": r["ts_code"] == ts_code,
            "revenue": None if pd.isna(r["rev"]) else round(float(r["rev"]) / 1e8, 1),
            "n_income": None if pd.isna(r["n_income"]) else round(float(r["n_income"]) / 1e8, 2),
            "rev_yoy": None if pd.isna(r["rev_yoy"]) else float(r["rev_yoy"]),
            "ni_yoy": None if pd.isna(r["ni_yoy"]) else float(r["ni_yoy"]),
            "net_margin": None if pd.isna(r["net_margin"]) else float(r["net_margin"]),
            "roe": None if pd.isna(r["roe"]) else float(r["roe"]),
            "debt_ratio": None if pd.isna(r["debt_ratio"]) else float(r["debt_ratio"]),
            "ocf_ni": None if pd.isna(r["ocf_ni"]) else float(r["ocf_ni"]),
        }
        for _, r in merged.iterrows()
    ]

    # 目标股票近 5 年营收/净利趋势 + 行业中位数
    years_col, stock_rev, stock_ni, med_rev, med_ni = [], [], [], [], []
    for y in range(int(latest_year[:4]) - 4, int(latest_year[:4]) + 1):
        ye = f"{y}1231"
        rows = _year_rows(inc_a, ye)
        if rows.empty:
            continue
        years_col.append(str(y))
        rows = rows.copy()
        rows["rev"] = rows["total_revenue"].combine_first(rows["revenue"]) if "revenue" in rows.columns else rows["total_revenue"]
        tgt = rows[rows["ts_code"] == ts_code]
        stock_rev.append(round(float(tgt["rev"].iloc[0]) / 1e8, 1) if not tgt.empty and pd.notna(tgt["rev"].iloc[0]) else None)
        stock_ni.append(round(float(tgt["n_income"].iloc[0]) / 1e8, 2) if not tgt.empty and pd.notna(tgt["n_income"].iloc[0]) else None)
        med_rev.append(round(float(rows["rev"].median()) / 1e8, 1) if rows["rev"].notna().any() else None)
        med_ni.append(round(float(rows["n_income"].median()) / 1e8, 2) if rows["n_income"].notna().any() else None)

    return {
        "ts_code": ts_code,
        "name": names.get(ts_code) or basic.iloc[0].get("name"),
        "industry": industry,
        "year": latest_year[:4],
        "peers": table,
        "trend": {
            "years": years_col,
            "stock_revenue": stock_rev,
            "stock_n_income": stock_ni,
            "median_revenue": med_rev,
            "median_n_income": med_ni,
        },
    }


# ---------------------------------------------------------------------------
# 4. 组合相关性
# ---------------------------------------------------------------------------

def portfolio_correlation(ts_codes: List[str], days: int = 120) -> dict:
    """组合相关性矩阵 + 等权净值 + 单票风险收益 + 风险贡献。"""
    ts_codes = [c for c in dict.fromkeys(ts_codes) if c][:12]
    if len(ts_codes) < 2:
        return {"error": "至少提供 2 只股票"}

    start = (pd.Timestamp.today() - pd.Timedelta(days=int(days) * 2 + 15)).strftime("%Y%m%d")
    px = _data_reader.get_return_prices(ts_codes=ts_codes, start_date=start)
    if px.empty:
        return {"error": "无行情数据"}
    px = px.sort_values("trade_date")
    pivot = px.pivot_table(index="trade_date", columns="ts_code", values="close").dropna()
    pivot = pivot.tail(int(days))
    if len(pivot) < 20 or pivot.shape[1] < 2:
        return {"error": "有效样本不足"}

    rets = pivot.pct_change().dropna()
    corr = rets.corr()

    eq_nav = (1 + rets.mean(axis=1)).cumprod()
    nav = [ {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for d, v in eq_nav.items() ]

    stats = []
    ann = 252
    for code in pivot.columns:
        r = rets[code]
        cum = float(pivot[code].iloc[-1] / pivot[code].iloc[0] - 1) * 100
        vol = float(r.std() * np.sqrt(ann) * 100)
        dd = float((pivot[code] / pivot[code].cummax() - 1).min() * 100)
        stats.append({
            "ts_code": code,
            "name": None,
            "cum_return": round(cum, 2),
            "ann_vol": round(vol, 2),
            "sharpe": round(float(r.mean() / r.std() * np.sqrt(ann)), 2) if r.std() > 0 else None,
            "max_drawdown": round(dd, 2),
        })

    # 风险贡献：等权组合方差分解 w_i * (Σw)_i / σ_p²
    w = np.array([1 / rets.shape[1]] * rets.shape[1])
    cov = rets.cov().values * ann
    port_var = float(w @ cov @ w)
    if port_var > 0:
        mcr = cov @ w
        contrib = (w * mcr) / port_var
    else:
        contrib = np.zeros(len(w))
    order = list(pivot.columns)
    for s, c in zip(stats, contrib):
        s["risk_contrib"] = round(float(c) * 100, 1)

    names = _names_map(order)
    for s in stats:
        s["name"] = names.get(s["ts_code"])

    # 平均相关系数（去对角线）
    cm = corr.values
    n = cm.shape[0]
    avg_corr = float((cm.sum() - n) / (n * (n - 1))) if n > 1 else None

    return {
        "days": len(pivot),
        "start_date": pivot.index[0].strftime("%Y-%m-%d"),
        "end_date": pivot.index[-1].strftime("%Y-%m-%d"),
        "codes": order,
        "corr_matrix": [[round(float(v), 3) for v in row] for row in cm],
        "avg_corr": round(avg_corr, 3),
        "nav": nav,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# 5. 历史日内统计
# ---------------------------------------------------------------------------

def intraday_stats(ts_code: str, days: int = 60) -> dict:
    """5 分钟 K 线的日内结构：成交量分布 / 隔夜-日内拆分 / 尾盘动量。"""
    mr = _data_reader.get_minute_reader()
    start = (pd.Timestamp.today() - pd.Timedelta(days=int(days) * 2 + 15)).strftime("%Y-%m-%d")
    bars = mr.get_data(ts_code=ts_code, period_type="5min", start_time=start)
    if bars.empty:
        return {"error": "无 5 分钟数据（覆盖 2026-04 起）"}

    bars = bars.sort_values("datetime").copy()
    bars["date"] = bars["datetime"].dt.strftime("%Y-%m-%d")
    bars["hm"] = bars["datetime"].dt.strftime("%H:%M")

    vol_profile = bars.groupby("hm")["volume"].mean()
    volume_profile = [{"time": t, "avg_vol": round(float(v), 0)} for t, v in vol_profile.items()]

    day_groups = bars.groupby("date")
    rows = []
    daily = _data_reader.get_daily(ts_codes=[ts_code], start_date=start)
    prev_close_map = {}
    if not daily.empty:
        d = daily.sort_values("trade_date")
        closes = d.set_index(d["trade_date"].dt.strftime("%Y-%m-%d"))["close"]
        prev_close_map = closes.shift(1).to_dict()

    for date, g in day_groups:
        if len(g) < 20:
            continue
        open_px = float(g.iloc[0]["open"])
        close_px = float(g.iloc[-1]["close"])
        prev_close = prev_close_map.get(date)
        tail = g[g["hm"] >= "14:30"]
        rows.append({
            "date": date,
            "overnight": (open_px / prev_close - 1) * 100 if prev_close else None,
            "intraday": (close_px / open_px - 1) * 100,
            "tail30": (close_px / float(tail.iloc[0]["open"]) - 1) * 100 if not tail.empty else None,
        })

    def _agg(key: str) -> dict:
        vals = [r[key] for r in rows if r[key] is not None and not np.isnan(r[key])]
        if not vals:
            return {"mean": None, "win_rate": None, "std": None}
        arr = np.array(vals)
        return {
            "mean": round(float(arr.mean()), 3),
            "std": round(float(arr.std()), 3),
            "win_rate": round(float((arr > 0).mean() * 100), 1),
        }

    scatter = [
        {"date": r["date"], "overnight": None if r["overnight"] is None else round(r["overnight"], 2),
         "intraday": round(r["intraday"], 2)}
        for r in rows
    ]
    return {
        "ts_code": ts_code,
        "name": _names_map([ts_code]).get(ts_code),
        "days": len(rows),
        "start_date": rows[0]["date"] if rows else None,
        "end_date": rows[-1]["date"] if rows else None,
        "volume_profile": volume_profile,
        "overnight": _agg("overnight"),
        "intraday": _agg("intraday"),
        "tail30": _agg("tail30"),
        "scatter": scatter,
    }


# ---------------------------------------------------------------------------
# 6. 事件复盘
# ---------------------------------------------------------------------------

def event_archive_dates() -> dict:
    """事件档案可用日期（按类型）。"""
    base = os.path.join(_data_reader.data_dir, "event_archive")
    result = {}
    if not os.path.isdir(base):
        return result
    for t in EVENT_ARCHIVE_TYPES:
        dirs = sorted(glob.glob(os.path.join(base, t, "date=*")))
        dates = [d.split("date=")[1] for d in dirs]
        if dates:
            result[t] = {"label": EVENT_ARCHIVE_LABELS.get(t, t), "dates": dates}
    return result


def event_replay(date: str) -> dict:
    """某交易日的事件全景：涨停/跌停/炸板/天梯/龙虎榜/情绪。"""
    base = os.path.join(_data_reader.data_dir, "event_archive")
    if not re_valid_date(date):
        return {"error": "日期格式应为 YYYYMMDD"}
    out = {"date": date, "sections": {}}
    for t in EVENT_ARCHIVE_TYPES:
        path = os.path.join(base, t, f"date={date}", "data.parquet")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_parquet(path)
        except Exception as e:
            logger.warning(f"读取事件档案失败 {path}: {e}")
            continue
        out["sections"][t] = {
            "label": EVENT_ARCHIVE_LABELS.get(t, t),
            "count": len(df),
            "rows": _sanitize_records(df, limit=200),
        }
    if not out["sections"]:
        out["error"] = f"{date} 无归档事件"
    return out


def re_valid_date(date: str) -> bool:
    return bool(isinstance(date, str) and len(date) == 8 and date.isdigit())
