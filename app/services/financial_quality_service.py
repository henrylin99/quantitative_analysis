"""财务质量分析服务：多年质量趋势评分 + 全市场财务异动扫描。

- quality_trend(ts_code)：单只股票近 10 个年报的杜邦分解趋势（ROE →
  净利率 × 资产周转率 × 权益乘数）+ 现金流含量 + 逐期质量分。
- anomaly_scan()：全市场最新年报截面扫描四类经典财务异动（应收/存货
  增速与营收背离、利润与现金流背离、毛利率骤降），输出异动名单。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader
from app.services.stock_name_registry import get_stock_name_registry

_ANOMALY_TOP_N = 60
_SCAN_YEARS = 3  # 市场级扫描只读最近 N 个年度分区，控制读取量

# 质量分规则权重（每条 1 分，满分 5 → 折算百分制）
_QUALITY_RULES = [
    ("roe", "ROE ≥ 10%"),
    ("cashflow", "经营现金流 / 净利润 ≥ 0.5"),
    ("net_margin", "净利率 ≥ 5%"),
    ("receiv_ok", "应收增速 ≤ 营收增速"),
    ("gross_margin", "毛利率 ≥ 20%"),
]


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def _latest_per_period(df: pd.DataFrame) -> pd.DataFrame:
    """同一期财报多版本时取 update_flag 最大的一行。"""
    if df.empty:
        return df
    if "update_flag" in df.columns:
        df = df.sort_values("update_flag").groupby(["ts_code", "end_date"], as_index=False).last()
    else:
        df = df.groupby(["ts_code", "end_date"], as_index=False).last()
    return df


def _annual(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "end_date" not in df.columns:
        return df
    return df[df["end_date"].astype(str).str.endswith("1231")].copy()


def _yoy(series: pd.Series) -> pd.Series:
    return series / series.shift(1).replace(0, np.nan) - 1


class FinancialQualityService:
    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()

    # ------------------------------------------------------------------
    # 单票质量趋势
    # ------------------------------------------------------------------
    def quality_trend(self, ts_code: str) -> Dict[str, Any]:
        income = self.data_reader.get_income_statement([ts_code])
        balance = self.data_reader.get_balance_sheet([ts_code])
        cash = self.data_reader.get_cash_flow([ts_code])
        if income.empty:
            return {"error": "无利润表数据"}

        income = _annual(_latest_per_period(income)).tail(11).reset_index(drop=True)
        balance = _annual(_latest_per_period(balance)) if not balance.empty else pd.DataFrame()
        cash = _annual(_latest_per_period(cash)) if not cash.empty else pd.DataFrame()
        if len(income) < 2:
            return {"error": "年报期数不足（至少 2 期）"}

        bal_by_year = {str(r["end_date"])[:4]: r for _, r in balance.iterrows()} \
            if not balance.empty else {}
        cash_by_year = {str(r["end_date"])[:4]: r for _, r in cash.iterrows()} \
            if not cash.empty else {}

        rows: List[Dict[str, Any]] = []
        for i in range(1, len(income)):
            cur = income.iloc[i]
            prev = income.iloc[i - 1]
            year = str(cur["end_date"])[:4]
            bal = bal_by_year.get(year)
            bal_prev = bal_by_year.get(str(prev["end_date"])[:4])
            cf = cash_by_year.get(year)

            revenue = float(cur.get("revenue") or 0)
            profit = float(cur.get("n_income_attr_p") or 0)
            equity = float(bal.get("total_hldr_eqy_inc_min_int")) if bal is not None else np.nan
            equity_prev = float(bal_prev.get("total_hldr_eqy_inc_min_int")) \
                if bal_prev is not None else np.nan
            total_assets = float(bal.get("total_assets")) if bal is not None else np.nan
            receiv = float(bal.get("accounts_receiv")) if bal is not None else np.nan
            receiv_prev = float(bal_prev.get("accounts_receiv")) if bal_prev is not None else np.nan
            invent = float(bal.get("inventories")) if bal is not None else np.nan
            invent_prev = float(bal_prev.get("inventories")) if bal_prev is not None else np.nan
            oper_cash = float(cf.get("n_cashflow_act")) if cf is not None else np.nan

            equity_avg = np.nanmean([equity, equity_prev]) if not np.isnan(equity) else np.nan
            revenue_prev = float(prev.get("revenue") or 0)

            roe = profit / equity_avg if equity_avg and equity_avg > 0 else np.nan
            net_margin = profit / revenue if revenue else np.nan
            oper_cost = cur.get("oper_cost")
            gross_margin = (revenue - float(oper_cost)) / revenue \
                if revenue and pd.notna(oper_cost) else np.nan
            turnover = revenue / total_assets if total_assets and total_assets > 0 else np.nan
            leverage = total_assets / equity_avg if equity_avg and equity_avg > 0 else np.nan
            cash_ratio = oper_cash / profit if profit and profit > 0 and pd.notna(oper_cash) else np.nan

            def _pct_chg(cur_v, prev_v):
                if pd.isna(cur_v) or pd.isna(prev_v) or not prev_v:
                    return np.nan
                return cur_v / prev_v - 1

            rows.append({
                "year": year,
                "revenue_yoy": _pct_chg(revenue, revenue_prev) * 100,
                "profit_yoy": _pct_chg(profit, float(prev.get("n_income_attr_p") or 0)) * 100,
                "roe": roe * 100,
                "net_margin": net_margin * 100,
                "gross_margin": gross_margin * 100,
                "asset_turnover": turnover,
                "equity_multiplier": leverage,
                "cash_to_profit": cash_ratio,
                "receiv_yoy": _pct_chg(receiv, receiv_prev) * 100,
                "inventory_yoy": _pct_chg(invent, invent_prev) * 100,
            })

        trend = pd.DataFrame(rows)
        # 逐期质量分（0-100）
        scores: List[int] = []
        for _, r in trend.iterrows():
            s = 0
            if pd.notna(r["roe"]) and r["roe"] >= 10:
                s += 1
            if pd.notna(r["cash_to_profit"]) and r["cash_to_profit"] >= 0.5:
                s += 1
            if pd.notna(r["net_margin"]) and r["net_margin"] >= 5:
                s += 1
            if pd.notna(r["receiv_yoy"]) and pd.notna(r["revenue_yoy"]) \
                    and r["receiv_yoy"] <= r["revenue_yoy"]:
                s += 1
            elif pd.isna(r["receiv_yoy"]) or pd.isna(r["revenue_yoy"]):
                s += 1  # 数据缺失不扣分
            if pd.notna(r["gross_margin"]) and r["gross_margin"] >= 20:
                s += 1
            scores.append(round(s / len(_QUALITY_RULES) * 100))
        trend["score"] = scores

        latest = trend.iloc[-1]
        # 趋势判定：近 3 期 ROE 与质量分
        recent = trend.tail(3)
        roe_trend = "下滑" if len(recent) >= 2 and recent["roe"].is_monotonic_decreasing \
            else ("改善" if len(recent) >= 2 and recent["roe"].is_monotonic_increasing else "平稳")
        score_trend = "下滑" if len(recent) >= 2 and recent["score"].is_monotonic_decreasing \
            else ("改善" if len(recent) >= 2 and recent["score"].is_monotonic_increasing else "平稳")

        return {
            "ts_code": ts_code,
            "years": trend.where(pd.notna(trend), None).to_dict(orient="records"),
            "latest": trend.where(pd.notna(trend), None).iloc[-1].to_dict(),
            "roe_trend": roe_trend,
            "score_trend": score_trend,
            "rules": [{"key": k, "label": v} for k, v in _QUALITY_RULES],
        }

    # ------------------------------------------------------------------
    # 全市场异动扫描（最新年报截面）
    # ------------------------------------------------------------------
    def anomaly_scan(self) -> Dict[str, Any]:
        income = self._read_recent_years("income_statement")
        balance = self._read_recent_years("balance_sheet")
        cash = self._read_recent_years("cash_flow")
        if income.empty:
            return {"error": "无利润表数据"}

        income = _annual(_latest_per_period(income))
        balance = _annual(_latest_per_period(balance)) if not balance.empty else pd.DataFrame()
        cash = _annual(_latest_per_period(cash)) if not cash.empty else pd.DataFrame()

        # 以利润表最新年报期为基准，其余表对齐同期
        latest_year = income["end_date"].astype(str).str[:4].max()
        inc = income[income["end_date"].astype(str).str[:4] == latest_year].set_index("ts_code")
        inc_prev = income[income["end_date"].astype(str).str[:4] == str(int(latest_year) - 1)] \
            .set_index("ts_code")
        bal = balance[balance["end_date"].astype(str).str[:4] == latest_year].set_index("ts_code") \
            if not balance.empty else pd.DataFrame()
        bal_prev = balance[balance["end_date"].astype(str).str[:4] == str(int(latest_year) - 1)] \
            .set_index("ts_code") if not balance.empty else pd.DataFrame()
        cf = cash[cash["end_date"].astype(str).str[:4] == latest_year].set_index("ts_code") \
            if not cash.empty else pd.DataFrame()
        cf_prev = cash[cash["end_date"].astype(str).str[:4] == str(int(latest_year) - 1)] \
            .set_index("ts_code") if not cash.empty else pd.DataFrame()

        def col(df_: pd.DataFrame, name: str) -> pd.Series:
            return df_[name] if not df_.empty and name in df_.columns else pd.Series(np.nan, index=inc.index)

        revenue = col(inc, "revenue").reindex(inc.index)
        revenue_prev = col(inc_prev, "revenue").reindex(inc.index)
        profit = col(inc, "n_income_attr_p").reindex(inc.index)
        oper_cost = col(inc, "oper_cost").reindex(inc.index)
        receiv = col(bal, "accounts_receiv").reindex(inc.index)
        receiv_prev = col(bal_prev, "accounts_receiv").reindex(inc.index)
        invent = col(bal, "inventories").reindex(inc.index)
        invent_prev = col(bal_prev, "inventories").reindex(inc.index)
        oper_cash = col(cf, "n_cashflow_act").reindex(inc.index)
        oper_cash_prev = col(cf_prev, "n_cashflow_act").reindex(inc.index)
        profit_prev = col(inc_prev, "n_income_attr_p").reindex(inc.index)

        panel = pd.DataFrame({
            "revenue": revenue, "revenue_yoy": _safe_div(revenue, revenue_prev) - 1,
            "profit_yoy": _safe_div(profit, profit_prev) - 1,
            "gross_margin": (revenue - oper_cost) / revenue.replace(0, np.nan),
            "receiv_yoy": _safe_div(receiv, receiv_prev) - 1,
            "inventory_yoy": _safe_div(invent, invent_prev) - 1,
            "cash_to_profit": _safe_div(oper_cash, profit.where(profit > 0)),
            "cash_to_profit_prev": _safe_div(oper_cash_prev, profit_prev.where(profit_prev > 0)),
        }).dropna(subset=["revenue"], how="all")
        panel = panel.replace([np.inf, -np.inf], np.nan)

        flags: Dict[str, pd.Series] = {
            "receiv_gap": (panel["receiv_yoy"] - panel["revenue_yoy"] > 0.20)
                          & panel["receiv_yoy"].notna(),
            "inventory_gap": (panel["inventory_yoy"] - panel["revenue_yoy"] > 0.20)
                             & panel["inventory_yoy"].notna(),
            "cash_diverge": (panel["cash_to_profit"] < 0.2)
                            & ((panel["cash_to_profit_prev"] < 0.2) | panel["cash_to_profit_prev"].isna())
                            & panel["cash_to_profit"].notna(),
            "margin_drop": (panel["gross_margin"].notna())
                           & (panel["gross_margin"] < 0.15),
        }
        flag_labels = {
            "receiv_gap": "应收增速超营收20pct+",
            "inventory_gap": "存货增速超营收20pct+",
            "cash_diverge": "利润为正但现金流连续偏弱",
            "margin_drop": "毛利率<15%",
        }
        any_flag = pd.concat(flags.values(), axis=1).any(axis=1)
        flagged = panel[any_flag].copy()
        for k in flags:
            flagged[k] = flags[k].reindex(flagged.index).fillna(False)

        # 命中数多者排前
        flagged["n_flags"] = flagged[list(flags)].sum(axis=1)
        flagged = flagged.sort_values(["n_flags", "revenue"], ascending=[False, False]).head(_ANOMALY_TOP_N)

        try:
            name_map = get_stock_name_registry().name_map()
        except Exception:
            name_map = {}

        rows = []
        for code, r in flagged.iterrows():
            rows.append({
                "ts_code": code,
                "name": name_map.get(str(code)),
                "revenue_yoy": round(r["revenue_yoy"] * 100, 1) if pd.notna(r["revenue_yoy"]) else None,
                "receiv_yoy": round(r["receiv_yoy"] * 100, 1) if pd.notna(r["receiv_yoy"]) else None,
                "inventory_yoy": round(r["inventory_yoy"] * 100, 1) if pd.notna(r["inventory_yoy"]) else None,
                "gross_margin": round(r["gross_margin"] * 100, 1) if pd.notna(r["gross_margin"]) else None,
                "cash_to_profit": round(r["cash_to_profit"], 2) if pd.notna(r["cash_to_profit"]) else None,
                "flags": [flag_labels[k] for k in flags if bool(r[k])],
                "n_flags": int(r["n_flags"]),
            })

        return {
            "report_year": latest_year,
            "universe": int(len(panel)),
            "flag_labels": flag_labels,
            "counts": {k: int(v.sum()) for k, v in flags.items()},
            "rows": rows,
            "total_flagged": int(any_flag.sum()),
        }

    # ------------------------------------------------------------------
    def _read_recent_years(self, table: str) -> pd.DataFrame:
        """只读最近 N 个年度分区，控制全市场扫描的读取量。"""
        import glob
        import os

        base = os.path.join(self.data_reader.data_dir, table)
        years = sorted(
            int(os.path.basename(p).split("=")[1])
            for p in glob.glob(os.path.join(base, "year=*")) if os.path.isdir(p)
        )
        frames = []
        for year in years[-_SCAN_YEARS:]:
            files = glob.glob(os.path.join(base, f"year={year}", "**", "data.parquet"),
                              recursive=True)
            for f in files:
                try:
                    frames.append(pd.read_parquet(f))
                except Exception as e:
                    logger.warning(f"读取 {f} 失败: {e}")
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        if "report_type" in df.columns:
            df = df[df["report_type"].astype(str) == "1"]
        return df
