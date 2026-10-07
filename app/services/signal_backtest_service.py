"""信号历史有效性回测：对已上线信号做前向收益验证。

- ChipSignalBacktestService：三类筹码信号（挤压/共振/背离）在历史每一天的
  截面上重算（阈值与 ChipSignalService 完全一致），统计信号触发后 5/10/20
  交易日的前向收益、胜率与相对 universe 等权的超额。
- AnomalyForwardService：财务异动名单（最新年报四类异动）按实际披露日
  （f_ann_date）统计披露后 5/10/20/60 交易日的前向收益，异动组 vs 同期
  universe 等权。

口径（与 quantile_portfolio_backtest 一致，无前视）：
- 信号/异动在 T 日（或披露日）只用当时可得信息判定；
- T+1 开盘入场、T+1+H 开盘出场（开—开）；
- 基准 = 同一入场出场规则下的全 universe 等权日均收益，超额 = 信号组日均 − 基准日均。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader

_CACHE_TTL_SECONDS = 3600.0
_MIN_EVENTS_PER_DAY = 3  # 当日触发数低于该值的日子不纳入日均统计（样本太少）
_HORIZONS = (5, 10, 20)
_ANOMALY_HORIZONS = (5, 10, 20, 60)

# 与 ChipSignalService 相同的信号阈值（保持两处一致：改动需同步）
_SQUEEZE_WINNER_MIN = 60.0
_SQUEEZE_CONC_QUANTILE = 0.20
_SQUEEZE_VOLUME_RATIO_MAX = 0.85
_SQUEEZE_PCT5D_MAX = 0.10
_RESONANCE_WINNER_LO = 30.0
_RESONANCE_WINNER_HI = 70.0
_DIVERGENCE_PCT5D_MIN = 0.03
_DIVERGENCE_WINNER_MIN = 70.0

_SIGNAL_LABELS = {
    "squeeze": "筹码挤压蓄势",
    "resonance": "资金×筹码多头共振",
    "divergence": "量价资金背离预警",
}


def _pivot_last(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """宽表化：行=trade_date（统一转 Timestamp），列=ts_code，同格取最后一行。"""
    out = df.pivot_table(index="trade_date", columns="ts_code",
                         values=value_col, aggfunc="last").sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def _daily_stats(day_mean: pd.Series, day_excess: pd.Series,
                 day_count: pd.Series, uni_mean: pd.Series) -> Dict[str, Any]:
    """一组日度收益序列的汇总统计。day_mean/day_excess 已剔除事件数不足的日子。"""
    valid = day_mean.dropna()
    excess = day_excess.dropna()
    nav = float((1 + valid).prod())
    uni_nav = float((1 + uni_mean.reindex(valid.index)).prod())
    if len(excess) >= 2 and excess.std() > 0:
        t_stat = float(excess.mean() / excess.std() * np.sqrt(len(excess)))
    else:
        t_stat = None
    return {
        "n_days": int(len(valid)),
        "n_events": int(day_count.sum()),
        "avg_events": round(float(day_count.mean()), 1) if len(day_count) else 0,
        "mean_ret_bp": round(float(valid.mean()) * 1e4, 2) if len(valid) else None,
        "median_ret_bp": round(float(valid.median()) * 1e4, 2) if len(valid) else None,
        "win_rate": round(float((valid > 0).mean()) * 100, 1) if len(valid) else None,
        "excess_bp": round(float(excess.mean()) * 1e4, 2) if len(excess) else None,
        "excess_t": round(t_stat, 2) if t_stat is not None else None,
        "worst_ret_bp": round(float(valid.min()) * 1e4, 2) if len(valid) else None,
        "total_ret_pct": round((nav - 1) * 100, 2) if len(valid) else None,
        "uni_total_ret_pct": round((uni_nav - 1) * 100, 2) if len(valid) else None,
        "nav": round(nav, 4) if len(valid) else None,
        "uni_nav": round(uni_nav, 4) if len(valid) else None,
    }


class ChipSignalBacktestService:
    """三类筹码信号的历史前向收益验证。"""

    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at: float = 0.0

    def run(self, months: int = 12, force_refresh: bool = False) -> Dict[str, Any]:
        import time

        months = max(3, min(int(months or 12), 24))
        if not force_refresh and self._cache is not None \
                and self._cache.get("months") == months \
                and time.monotonic() - self._cache_at < _CACHE_TTL_SECONDS:
            return self._cache

        result = self._run(months)
        if "error" not in result:
            result["months"] = months
            self._cache = result
            self._cache_at = time.monotonic()
        return result

    # ------------------------------------------------------------------
    def _run(self, months: int) -> Dict[str, Any]:
        end = datetime.now()
        eval_start = end - timedelta(days=months * 31)
        # 预热：量能比需要 20 交易日、5日涨幅/获利盘变化需要 5 交易日
        warm_start = eval_start - timedelta(days=45)

        try:
            cyq = self.data_reader.get_cyq_perf(ts_codes=None, start_date=warm_start.strftime("%Y-%m-%d"),
                                                end_date=end.strftime("%Y-%m-%d"))
            daily = self.data_reader.get_daily(ts_codes=None, start_date=warm_start.strftime("%Y-%m-%d"),
                                               end_date=end.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error(f"信号回测读取行情/筹码失败: {e}")
            return {"error": f"读取行情数据失败: {e}"}
        if cyq.empty or daily.empty:
            return {"error": "筹码或行情数据为空"}

        try:
            flow = self.data_reader.get_moneyflow(ts_codes=None, start_date=eval_start.strftime("%Y-%m-%d"),
                                                  end_date=end.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.warning(f"信号回测读取资金流失败（共振/背离信号将缺失）: {e}")
            flow = pd.DataFrame()

        # ---------- 宽面板 ----------
        cyq = cyq.sort_values(["ts_code", "trade_date"])
        winner_w = _pivot_last(cyq, "winner_rate")
        conc_w = (_pivot_last(cyq, "cost_95pct") - _pivot_last(cyq, "cost_5pct")) \
            / _pivot_last(cyq, "cost_50pct")
        winner_chg_w = winner_w.diff(5)

        daily = daily.sort_values(["ts_code", "trade_date"])
        close_w = _pivot_last(daily, "close")
        open_w = _pivot_last(daily, "open")
        vol_w = _pivot_last(daily, "vol")
        pct5_w = close_w.pct_change(5)
        vol_ratio_w = vol_w.rolling(5).mean() / vol_w.rolling(20).mean()

        # 评估窗口：信号日必须有筹码截面（cyq 是三类信号的公共依赖）
        dates = [d for d in winner_w.index
                 if pd.notna(d) and eval_start <= pd.Timestamp(d) <= pd.Timestamp(end)]
        # 出场日需要 open_w 里也有数据（否则前向收益算不出来）
        dates = [d for d in dates if d in open_w.index]
        if not dates:
            return {"error": "评估窗口内无有效截面"}

        def align(w: pd.DataFrame) -> pd.DataFrame:
            return w.reindex(index=dates)

        winner = align(winner_w)
        conc = align(conc_w)
        winner_chg = align(winner_chg_w)
        pct5 = align(pct5_w)
        vol_ratio = align(vol_ratio_w)
        open_al = align(open_w)

        net5 = net_last = None
        if not flow.empty:
            flow = flow.copy()
            flow["main_net"] = (flow["buy_lg_amount"] + flow["buy_elg_amount"]
                                - flow["sell_lg_amount"] - flow["sell_elg_amount"])
            net_w = _pivot_last(flow, "main_net")
            net5 = align(net_w.rolling(5, min_periods=3).sum())
            net_last = align(net_w)

        # ---------- 信号掩码（与 ChipSignalService 同规则） ----------
        conc_thresh = conc.quantile(_SQUEEZE_CONC_QUANTILE, axis=1)

        squeeze = (winner >= _SQUEEZE_WINNER_MIN) & conc.le(conc_thresh, axis=0) \
            & (vol_ratio <= _SQUEEZE_VOLUME_RATIO_MAX) & (pct5.fillna(0) <= _SQUEEZE_PCT5D_MAX)
        if net5 is not None:
            resonance = (net5 > 0) & (net_last > 0) & (winner_chg > 0) \
                & (winner >= _RESONANCE_WINNER_LO) & (winner <= _RESONANCE_WINNER_HI) \
                & (pct5.fillna(0) > 0)
            divergence = (pct5.fillna(0) >= _DIVERGENCE_PCT5D_MIN) & (net5 < 0) \
                & (winner >= _DIVERGENCE_WINNER_MIN)
        else:
            empty = pd.DataFrame(False, index=dates, columns=winner.columns)
            resonance = empty
            divergence = empty.copy()

        # ---------- 前向收益（T+1 开 → T+1+H 开） ----------
        entry = open_al.shift(-1)
        uni_navs: Dict[int, pd.Series] = {}
        fwd: Dict[int, pd.DataFrame] = {}
        for h in _HORIZONS:
            fwd[h] = open_al.shift(-(1 + h)) / entry - 1
            uni_navs[h] = fwd[h].mean(axis=1)

        masks = {"squeeze": squeeze, "resonance": resonance, "divergence": divergence}
        signals: Dict[str, Any] = {}
        nav_series: Dict[str, Dict[str, List[Optional[float]]]] = {}
        for name, mask in masks.items():
            counts = mask.sum(axis=1)
            per_horizon = {}
            navs_out: Dict[str, List[Optional[float]]] = {}
            for h in _HORIZONS:
                f = fwd[h]
                hit_sum = f.where(mask)
                day_mean_full = hit_sum.mean(axis=1)
                day_mean = day_mean_full.where(counts >= _MIN_EVENTS_PER_DAY)
                day_excess = (day_mean - uni_navs[h]).where(counts >= _MIN_EVENTS_PER_DAY)
                per_horizon[f"h{h}"] = _daily_stats(day_mean, day_excess, counts, uni_navs[h])
                # 净值：按 H 日不重叠调仓复利（重叠持有期逐日复利会指数级虚高）。
                # 锚点 = 每 H 个交易日取一个信号日，锚点收益 = 该日信号的 H 日平均持有收益
                step_dates = dates[::h]
                step_ret = day_mean_full.reindex(step_dates).dropna()
                step_uni = uni_navs[h].reindex(step_ret.index)
                nav = (1 + step_ret).cumprod()
                uni = (1 + step_uni).cumprod()
                navs_out[f"h{h}"] = {
                    "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in step_ret.index],
                    "nav": [round(float(v), 4) for v in nav],
                    "uni_nav": [round(float(v), 4) for v in uni],
                }
            signals[name] = {"label": _SIGNAL_LABELS[name], "horizons": per_horizon}
            nav_series[name] = navs_out

        return {
            "meta": {
                "start": pd.Timestamp(dates[0]).strftime("%Y-%m-%d"),
                "end": pd.Timestamp(dates[-1]).strftime("%Y-%m-%d"),
                "n_days": len(dates),
                "universe_avg_count": round(float(winner.notna().sum(axis=1).mean()), 0),
                "horizons": list(_HORIZONS),
                "min_events_per_day": _MIN_EVENTS_PER_DAY,
                "has_moneyflow": net5 is not None,
            },
            "signals": signals,
            "nav_series": nav_series,
            "definitions": {
                "squeeze": f"获利盘≥{_SQUEEZE_WINNER_MIN}% 且集中度≤截面{int(_SQUEEZE_CONC_QUANTILE*100)}%分位 且量能收缩 且5日涨幅≤{_SQUEEZE_PCT5D_MAX:.0%}",
                "resonance": "近5日主力净额>0 且最新一日仍净流入 获利盘5日抬升且处于30%~70% 5日上涨",
                "divergence": f"5日涨幅≥{_DIVERGENCE_PCT5D_MIN:.0%} 且近5日主力净流出 获利盘≥{_DIVERGENCE_WINNER_MIN}%",
            },
        }


class AnomalyForwardService:
    """财务异动名单按实际披露日的前向收益统计。"""

    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at: float = 0.0

    def run(self, force_refresh: bool = False) -> Dict[str, Any]:
        import time

        if not force_refresh and self._cache is not None \
                and time.monotonic() - self._cache_at < _CACHE_TTL_SECONDS:
            return self._cache

        result = self._run()
        if "error" not in result:
            self._cache = result
            self._cache_at = time.monotonic()
        return result

    # ------------------------------------------------------------------
    def _run(self) -> Dict[str, Any]:
        from app.services.financial_quality_service import FinancialQualityService, _annual, _latest_per_period

        fq = FinancialQualityService(self.data_reader)
        income = _annual(_latest_per_period(fq._read_recent_years("income_statement")))
        balance = _annual(_latest_per_period(fq._read_recent_years("balance_sheet")))
        cash = _annual(_latest_per_period(fq._read_recent_years("cash_flow")))
        if income.empty:
            return {"error": "无利润表数据"}

        latest_year = income["end_date"].astype(str).str[:4].max()
        # 异动判定与 FinancialQualityService.anomaly_scan 完全同规则，
        # 这里额外保留披露日（f_ann_date → ann_date 兜底）
        scan = fq.anomaly_scan()
        if "error" in scan:
            return scan
        flagged_codes = {r["ts_code"] for r in scan["rows"]}
        # anomaly_scan 只返回 top 60 行，重新按全量 flags 计算一份（含全部命中）
        panel = self._full_flags(income, balance, cash, latest_year)
        if panel.empty:
            return {"error": "异动面板为空"}

        ann = income[income["end_date"].astype(str).str[:4] == latest_year]
        ann_map = {}
        for _, r in ann.iterrows():
            d = r.get("f_ann_date") or r.get("ann_date")
            if d is not None and str(d).strip():
                ann_map[r["ts_code"]] = str(d)[:10]

        panel = panel[panel.index.map(lambda c: c in ann_map)]
        if panel.empty:
            return {"error": "异动名单缺少披露日期"}

        # 前向收益：披露日 T 收盘后可得 → T+1 开盘入场
        start = min(ann_map.values())
        end = datetime.now().strftime("%Y-%m-%d")
        daily = self.data_reader.get_daily(ts_codes=sorted(ann_map), start_date=start, end_date=end)
        if daily.empty:
            return {"error": "无行情数据"}
        open_w = _pivot_last(daily.sort_values(["ts_code", "trade_date"]), "open")
        dates_idx = open_w.index

        event_rows = []
        for code, r in panel.iterrows():
            if code not in open_w.columns:
                continue  # 窗口内无行情（长期停牌/退市等）
            d = pd.Timestamp(ann_map[code])
            if d not in dates_idx:
                continue
            pos = dates_idx.get_loc(d)
            for h in _ANOMALY_HORIZONS:
                j = pos + 1 + h
                if j >= len(dates_idx):
                    continue
                event_rows.append({
                    "ts_code": code,
                    "ann_date": ann_map[code],
                    "h": h,
                    "ret": float(open_w.iloc[j][code] / open_w.iloc[pos + 1][code] - 1)
                    if pd.notna(open_w.iloc[j][code]) and pd.notna(open_w.iloc[pos + 1][code]) else np.nan,
                    **{k: (bool(r[k]) if pd.notna(r[k]) else False) for k in panel.columns},
                })
        ev = pd.DataFrame(event_rows)
        if ev.empty:
            return {"error": "披露日不在行情覆盖范围内"}

        # 同期 universe 基准：每个披露日全市场等权同期限收益
        all_daily = self.data_reader.get_daily(ts_codes=None, start_date=start, end_date=end)
        all_open = _pivot_last(all_daily.sort_values(["ts_code", "trade_date"]), "open")
        uni_by_key: Dict[tuple, float] = {}
        for h in _ANOMALY_HORIZONS:
            f = all_open.shift(-(1 + h)) / all_open.shift(-1) - 1
            for d in ev["ann_date"].unique():
                dt = pd.Timestamp(d)
                if dt in f.index:
                    uni_by_key[(h, d)] = float(f.loc[dt].mean())
        ev["uni_ret"] = [uni_by_key.get((r["h"], r["ann_date"]), np.nan) for _, r in ev.iterrows()]
        ev["excess"] = ev["ret"] - ev["uni_ret"]

        flag_cols = ["receiv_gap", "inventory_gap", "cash_diverge", "margin_drop"]
        labels = scan.get("flag_labels", {})

        def _agg(sub: pd.DataFrame) -> Dict[str, Any]:
            ret = sub["ret"].dropna()
            exc = sub["excess"].dropna()
            return {
                "n": int(len(sub)),
                "mean_ret_bp": round(float(ret.mean()) * 1e4, 1) if len(ret) else None,
                "win_rate": round(float((ret > 0).mean()) * 100, 1) if len(ret) else None,
                "excess_bp": round(float(exc.mean()) * 1e4, 1) if len(exc) else None,
                "excess_t": round(float(exc.mean() / exc.std() * np.sqrt(len(exc))), 2)
                if len(exc) >= 2 and exc.std() > 0 else None,
            }

        groups: Dict[str, Any] = {}
        for col in flag_cols:
            groups[col] = {"label": labels.get(col, col),
                           "n_stocks": int(ev[ev[col]]["ts_code"].nunique())}
            for h in _ANOMALY_HORIZONS:
                groups[col][f"h{h}"] = _agg(ev[ev[col] & (ev["h"] == h)])
        clean = ev[~ev[flag_cols].any(axis=1)]
        groups["clean"] = {"label": "无异动（对照组）", "n_stocks": int(clean["ts_code"].nunique())}
        for h in _ANOMALY_HORIZONS:
            groups["clean"][f"h{h}"] = _agg(clean[clean["h"] == h])

        return {
            "report_year": scan.get("report_year"),
            "horizons": list(_ANOMALY_HORIZONS),
            "groups": groups,
            "note": "口径：披露日 T 的次一交易日开盘入场、T+1+H 开盘出场；基准为同规则全市场等权",
        }

    @staticmethod
    def _full_flags(income: pd.DataFrame, balance: pd.DataFrame,
                    cash: pd.DataFrame, latest_year: str) -> pd.DataFrame:
        """复算 anomaly_scan 的四类异动掩码（全量命中，不止 top 60）。"""
        def by_year(df: pd.DataFrame, year: str) -> pd.DataFrame:
            if df.empty:
                return pd.DataFrame()
            return df[df["end_date"].astype(str).str[:4] == year].set_index("ts_code")

        def col(df: pd.DataFrame, name: str, idx) -> pd.Series:
            if df.empty or name not in df.columns:
                return pd.Series(np.nan, index=idx)
            return df[name]

        inc = by_year(income, latest_year)
        idx = inc.index
        inc_prev = by_year(income, str(int(latest_year) - 1))
        bal = by_year(balance, latest_year)
        bal_prev = by_year(balance, str(int(latest_year) - 1))
        cf = by_year(cash, latest_year)
        cf_prev = by_year(cash, str(int(latest_year) - 1))

        def safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
            return a / b.replace(0, np.nan)

        revenue = col(inc, "revenue", idx)
        panel = pd.DataFrame({
            "revenue_yoy": safe_div(revenue, col(inc_prev, "revenue", idx)) - 1,
            "receiv_yoy": safe_div(col(bal, "accounts_receiv", idx), col(bal_prev, "accounts_receiv", idx)) - 1,
            "inventory_yoy": safe_div(col(bal, "inventories", idx), col(bal_prev, "inventories", idx)) - 1,
            "gross_margin": (revenue - col(inc, "oper_cost", idx)) / revenue.replace(0, np.nan),
            "cash_to_profit": safe_div(col(cf, "n_cashflow_act", idx), col(inc, "n_income_attr_p", idx).where(col(inc, "n_income_attr_p", idx) > 0)),
            "cash_to_profit_prev": safe_div(col(cf_prev, "n_cashflow_act", idx), col(inc_prev, "n_income_attr_p", idx).where(col(inc_prev, "n_income_attr_p", idx) > 0)),
        })
        panel = panel.replace([np.inf, -np.inf], np.nan)
        flags = pd.DataFrame(index=idx)
        flags["receiv_gap"] = (panel["receiv_yoy"] - panel["revenue_yoy"] > 0.20) & panel["receiv_yoy"].notna()
        flags["inventory_gap"] = (panel["inventory_yoy"] - panel["revenue_yoy"] > 0.20) & panel["inventory_yoy"].notna()
        flags["cash_diverge"] = (panel["cash_to_profit"] < 0.2) & panel["cash_to_profit"].notna() \
            & ((panel["cash_to_profit_prev"] < 0.2) | panel["cash_to_profit_prev"].isna())
        flags["margin_drop"] = panel["gross_margin"].notna() & (panel["gross_margin"] < 0.15)
        return flags
