"""行业轮动监测：动量 + 主力资金 + 估值分位三维评分。

对 stock_basic 的 Tushare 行业口径（每行业成分股等权）：
- 动量：行业日收益（成分股日收益等权均值）近 5/20 日累计；
- 资金：行业内个股主力净额（特大+大单）逐日合计，近 5/20 日累计；
- 估值：行业成分股 pe_ttm 中位数在自身近一年序列里的分位（低分位=便宜）。

评分 = z(动量20日) + z(资金5日) + z(资金20日) − z(估值分位)，
z 均为评估末日全行业截面 z-score。只读本地日频数据，无前视。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader

_CACHE_TTL_SECONDS = 3600.0
_MIN_MEMBERS = 10          # 行业成分股少于此数不参与评分（等权收益不稳定）
_MIN_FLOW_COVERAGE = 0.5   # 行业主力净额覆盖天数占比下限（无资金流数据时置空）
_TOP_BOTTOM_N = 5


def _zscore(series: pd.Series) -> pd.Series:
    std = series.std()
    if not np.isfinite(std) or std == 0:
        return series * 0.0
    return (series - series.mean()) / std


class IndustryRotationService:
    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()
        self._cache: Dict[int, Any] = {}
        self._cache_at: Dict[int, float] = {}

    def run(self, months: int = 12, force_refresh: bool = False) -> Dict[str, Any]:
        import time

        months = max(3, min(int(months or 12), 24))
        if not force_refresh and months in self._cache \
                and time.monotonic() - self._cache_at.get(months, 0) < _CACHE_TTL_SECONDS:
            return self._cache[months]

        result = self._run(months)
        if "error" not in result:
            result["months"] = months
            self._cache[months] = result
            self._cache_at[months] = time.monotonic()
        return result

    # ------------------------------------------------------------------
    def _run(self, months: int) -> Dict[str, Any]:
        end = datetime.now()
        eval_start = end - timedelta(days=months * 31)
        warm_start = eval_start - timedelta(days=60)  # 20日动量 + 滚动窗口预热

        basic = self.data_reader.get_stock_basic()
        if basic.empty or "industry" not in basic.columns:
            return {"error": "无 stock_basic 行业映射"}
        ind_map = basic.dropna(subset=["industry"]).set_index("ts_code")["industry"]

        try:
            daily = self.data_reader.get_daily(
                ts_codes=None, start_date=warm_start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error(f"行业轮动读取行情失败: {e}")
            return {"error": f"读取行情数据失败: {e}"}
        if daily.empty:
            return {"error": "行情数据为空"}

        daily = daily[daily["ts_code"].isin(ind_map.index)]
        close = daily.pivot_table(index="trade_date", columns="ts_code",
                                  values="close", aggfunc="last").sort_index()
        close.index = pd.to_datetime(close.index)
        stock_ret = close.pct_change()
        # 成分股日收益等权 → 行业日收益（逐日，PIT 成分=最新 stock_basic，无未来成分变化）
        ind_groups = pd.Series(ind_map)
        ind_ret = stock_ret.T.groupby(ind_groups).mean().T

        eval_dates = [d for d in ind_ret.index if pd.Timestamp(d) >= pd.Timestamp(eval_start)]
        if not eval_dates:
            return {"error": "评估窗口内无有效截面"}
        last = pd.Timestamp(eval_dates[-1])

        mom5 = ind_ret.rolling(5).sum()
        mom20 = ind_ret.rolling(20).sum()

        # 资金流
        flow5 = flow20 = None
        try:
            flow = self.data_reader.get_moneyflow(
                ts_codes=None, start_date=eval_start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"))
            if not flow.empty:
                flow = flow[flow["ts_code"].isin(ind_map.index)].copy()
                flow["main_net"] = (flow["buy_lg_amount"] + flow["buy_elg_amount"]
                                    - flow["sell_lg_amount"] - flow["sell_elg_amount"])
                net = flow.pivot_table(index="trade_date", columns="ts_code",
                                       values="main_net", aggfunc="last").sort_index()
                net.index = pd.to_datetime(net.index)
                ind_net = net.T.groupby(ind_groups).sum().T
                # 覆盖天数占比：净额非空天数 / 评估期交易日数
                coverage = ind_net.reindex(eval_dates).notna().mean()
                flow5 = ind_net.rolling(5, min_periods=3).sum().iloc[-1]
                flow20 = ind_net.rolling(20, min_periods=10).sum().iloc[-1]
                flow5[coverage < _MIN_FLOW_COVERAGE] = np.nan
                flow20[coverage < _MIN_FLOW_COVERAGE] = np.nan
        except Exception as e:
            logger.warning(f"行业轮动读取资金流失败（资金维度缺失）: {e}")

        # 估值：行业 pe_ttm 中位数序列 → 当前值在窗口内的历史分位
        pe_pct = None
        pe_med_now = None
        try:
            db = self.data_reader.get_daily_basic(
                ts_codes=None, start_date=eval_start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"))
            if not db.empty and "pe_ttm" in db.columns:
                db = db[db["ts_code"].isin(ind_map.index)]
                pe = db.pivot_table(index="trade_date", columns="ts_code",
                                    values="pe_ttm", aggfunc="last").sort_index()
                pe.index = pd.to_datetime(pe.index)
                pe_ind = pe.T.groupby(ind_groups).median().T
                pe_rank = pe_ind.rank(pct=True)  # 逐日截面分位：便宜=低
                pe_pct_now = pe_rank.iloc[-1]
                # 历史自分位：当前中位数在该行业自身窗口内的分位
                pe_med_now = pe_ind.iloc[-1]
                hist = pe_ind.apply(lambda s: (s < s.iloc[-1]).mean(), axis=0)
                pe_pct = pd.DataFrame({
                    "pe_med": pe_med_now,
                    "hist_pct": hist,        # 历史分位（越低越便宜）
                    "xs_rank": pe_pct_now,   # 当日截面分位
                })
        except Exception as e:
            logger.warning(f"行业轮动读取估值失败（估值维度缺失）: {e}")

        # ---------- 评分 ----------
        idx = ind_ret.columns
        mom20_now = mom20.iloc[-1]
        mom5_now = mom5.iloc[-1]
        members = ind_map.value_counts()  # 行业成分股数量

        score_df = pd.DataFrame(index=idx)
        score_df["mom5"] = mom5_now
        score_df["mom20"] = mom20_now
        score_df["flow5"] = flow5 if flow5 is not None else np.nan
        score_df["flow20"] = flow20 if flow20 is not None else np.nan
        if pe_pct is not None:
            score_df["pe_med"] = pe_pct["pe_med"]
            score_df["pe_hist_pct"] = pe_pct["hist_pct"]
            score_df["pe_xs_rank"] = pe_pct["xs_rank"]

        score_df = score_df.dropna(subset=["mom20"])
        score_df["n_members"] = members.reindex(score_df.index)
        score_df = score_df[score_df["n_members"] >= _MIN_MEMBERS]
        if score_df.empty:
            return {"error": "有效行业不足"}

        score_df["mom_z"] = _zscore(score_df["mom20"])
        if flow5 is not None:
            # 缺资金流覆盖的行业以截面中位数补齐（中性化处理，不给额外分）
            f5 = score_df["flow5"].fillna(score_df["flow5"].median())
            f20 = score_df["flow20"].fillna(score_df["flow20"].median())
            score_df["flow_z"] = _zscore(f5) + _zscore(f20)
        else:
            score_df["flow_z"] = np.nan
        score_df["value_z"] = -_zscore(score_df["pe_hist_pct"]) if "pe_hist_pct" in score_df else np.nan

        parts = [score_df["mom_z"]]
        for col in ("flow_z", "value_z"):
            if col in score_df.columns and score_df[col].notna().any():
                parts.append(score_df[col].fillna(score_df[col].median()))
        score_df["total_score"] = sum(parts)

        score_df = score_df.sort_values("total_score", ascending=False)
        score_df["rank"] = range(1, len(score_df) + 1)

        # 行业累计净值（评估窗口内），供 top/bottom 对比图
        ind_nav = (1 + ind_ret.reindex(eval_dates).fillna(0)).cumprod()

        def _row(name: str) -> Dict[str, Any]:
            r = score_df.loc[name]
            def num(v, digits=2, pct=False):
                if pd.isna(v):
                    return None
                return round(float(v) * (100 if pct else 1), digits)
            return {
                "industry": name,
                "n_members": int(r["n_members"]),
                "mom_5d": num(r["mom5"], pct=True),
                "mom_20d": num(r["mom20"], pct=True),
                "flow_5d": num(r["flow5"], 0),
                "flow_20d": num(r["flow20"], 0),
                "pe_med": num(r.get("pe_med", np.nan), 1),
                "pe_hist_pct": num(r.get("pe_hist_pct", np.nan), 3),
                "mom_z": num(r["mom_z"]),
                "flow_z": num(r["flow_z"]),
                "value_z": num(r["value_z"]),
                "total_score": num(r["total_score"]),
                "rank": int(r["rank"]),
            }

        top_names = list(score_df.index[:_TOP_BOTTOM_N])
        bottom_names = list(score_df.index[-_TOP_BOTTOM_N:])
        nav_chart = {
            "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in ind_nav.index],
            "top": {name: [round(float(v), 4) for v in ind_nav[name]] for name in top_names},
            "bottom": {name: [round(float(v), 4) for v in ind_nav[name]] for name in bottom_names},
        }

        return {
            "meta": {
                "eval_start": pd.Timestamp(eval_dates[0]).strftime("%Y-%m-%d"),
                "eval_end": last.strftime("%Y-%m-%d"),
                "n_industries": int(len(score_df)),
                "n_days": len(eval_dates),
                "has_moneyflow": flow5 is not None,
                "has_valuation": pe_pct is not None,
                "min_members": _MIN_MEMBERS,
            },
            "score_formula": "总评分 = z(20日动量) + z(5日主力净额) + z(20日主力净额) − z(PE历史分位)，均为行业截面 z-score",
            "rows": [_row(name) for name in score_df.index],
            "nav_chart": nav_chart,
        }
