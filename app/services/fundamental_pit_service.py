"""财务 PIT 因子库：三大报表按公告日打点 → 6 个基本面因子入 factor_values。

PIT 纪律（roadmap 批次四）：任一 trade_date T 的因子值只用 f_ann_date ≤ T
的报表——公告日之前的市场不知道该期数据，按期末日期对齐会引入前视。
更新/修订公告按"T 日已知的最新一版"取（那是当时市场上的真实信息集）。

6 因子（roadmap 4.3）：
- ocf_to_ni        经营现金流/归母净利润（现金转化能力，YTD 口径同比可比）
- accrual_ratio    应计质量 = (归母净利润 − 经营现金流)/总资产（越高越"纸面"）
- gross_margin_chg 毛利率同比变化（(营收−营业成本)/营收 − 一年前同期）
- leverage_chg     资产负债率同比变化
- asset_turnover_chg 资产周转率（YTD 营收/总资产）同比变化
- roe_chg          ROE（YTD 归母净利/归母权益）同比变化

同比 = 与 end_date 恰好早一年的报告期比；缺上年同期（次新股）→ 因子缺失，
不造假 0。零分母（净利润≈0、总资产缺失等）同样缺失。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

# 声明顺序即依赖表顺序
_STATEMENTS = {
    "income_statement": ["ts_code", "ann_date", "f_ann_date", "end_date",
                         "report_type", "revenue", "oper_cost", "n_income_attr_p"],
    "balance_sheet": ["ts_code", "ann_date", "f_ann_date", "end_date",
                      "report_type", "total_assets", "total_liab",
                      "total_hldr_eqy_exc_min_int"],
    "cash_flow": ["ts_code", "ann_date", "f_ann_date", "end_date",
                  "report_type", "n_cashflow_act"],
}

FUNDAMENTAL_PIT_FACTOR_IDS = (
    "ocf_to_ni",
    "accrual_ratio",
    "gross_margin_chg",
    "leverage_chg",
    "asset_turnover_chg",
    "roe_chg",
)


def _norm_date_str(series: pd.Series) -> pd.Series:
    """end_date/公告日在存量表里 YYYYMMDD 与 YYYY-MM-DD 混存，统一 YYYYMMDD。

    format="mixed" 必须：pandas 对混合格式按首元素推断，其余整列变 NaT。
    """
    return pd.to_datetime(series, errors="coerce", format="mixed").dt.strftime("%Y%m%d")


def _shift_year(ymd: str) -> str:
    """end_date 同比期：20260630 → 20250630（闰年 0229 → 平年缺失由 join 自然处理）。"""
    year = int(ymd[:4]) - 1
    rest = ymd[4:]
    if rest == "0229":
        return None  # 平年无 2 月 29 日，同比期不存在
    return f"{year}{rest}"


def _known_latest(df: pd.DataFrame, t: str) -> pd.DataFrame:
    """T 时点已知集：公告日 ≤ T 的行里，每个 (ts_code, end_date) 取最新公告版。

    去重必须在 T 过滤之后做——提前去重会丢掉修订前的原版，T 落在
    原公告与修订公告之间时就查不到任何已知版本（PIT 破坏）。
    """
    known = df[df["ann_ymd"] <= t]
    return (known.sort_values(["ts_code", "end_date", "ann_ymd"])
            .drop_duplicates(subset=["ts_code", "end_date"], keep="last"))


class FundamentalPitService:
    """三大报表 PIT 打点 → 基本面因子长表。"""

    def __init__(self, data_dir: Optional[str] = None, engine=None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir
        self._engine = engine
        self._statements: Optional[Dict[str, pd.DataFrame]] = None

    # ------------------------------------------------------------------
    def _load_statements(self) -> Dict[str, pd.DataFrame]:
        """三表一次性加载（只读所需列），report_type=1 合并口径 + 最新公告去重。"""
        if self._statements is not None:
            return self._statements
        loaded: Dict[str, pd.DataFrame] = {}
        for table, columns in _STATEMENTS.items():
            base = os.path.join(self.data_dir, table)
            try:
                df = pd.read_parquet(base, columns=columns)
            except Exception as e:
                logger.warning(f"[fund_pit] 读取 {table} 失败（相关因子缺失）: {e}")
                loaded[table] = pd.DataFrame()
                continue
            if df.empty:
                loaded[table] = pd.DataFrame()
                continue
            df = df[df["report_type"].astype(str) == "1"].copy()
            df["ann_eff"] = pd.to_datetime(
                df["f_ann_date"].fillna(df["ann_date"]), errors="coerce", format="mixed")
            df["end_date"] = _norm_date_str(df["end_date"])
            df = df.dropna(subset=["ann_eff", "end_date"])
            df["ann_ymd"] = df["ann_eff"].dt.strftime("%Y%m%d")
            # 不在加载期去重：修订公告必须保留全部版本，查询时按 T 时点取最新已知
            loaded[table] = df.drop(columns=["ann_eff"])
            logger.info(f"[fund_pit] {table} 加载 {len(loaded[table])} 行"
                        f"（report_type=1，含修订公告全部版本）")
        self._statements = loaded
        return loaded

    # ------------------------------------------------------------------
    def compute_for_date(self, trade_date: str) -> pd.DataFrame:
        """单交易日的 6 因子截面（长表：ts_code/factor_id/trade_date/factor_value）。"""
        tables = self._load_statements()
        inc, bal, cf = (tables.get("income_statement"), tables.get("balance_sheet"),
                        tables.get("cash_flow"))
        if inc is None or inc.empty:
            return pd.DataFrame()

        t = pd.Timestamp(trade_date).strftime("%Y%m%d")

        inc_k = _known_latest(inc, t)
        if inc_k.empty:
            return pd.DataFrame()
        # 每只股票 T 已知的最新报告期（cur）与同比期（prev，end_date 恰好早一年）
        cur = inc_k.sort_values(["ts_code", "end_date"]).groupby("ts_code").tail(1)
        cur = cur.set_index("ts_code")
        cur = cur.assign(prev_key=[_shift_year(e) if e else None for e in cur["end_date"]])
        cur = cur.dropna(subset=["prev_key"])
        if cur.empty:
            return pd.DataFrame()

        cur_keys = pd.MultiIndex.from_arrays([cur.index, cur["end_date"]])
        prev_keys = pd.MultiIndex.from_arrays([cur.index, cur["prev_key"]])

        def _join(df: pd.DataFrame, keys, cols, suffix: str) -> pd.DataFrame:
            """按 (ts_code, end_date) 键连指定列；df 空/列缺时以 NaN 占位。"""
            if df is None or df.empty:
                return pd.DataFrame(np.nan, index=cur.index,
                                    columns=[c + suffix for c in cols])
            got = _known_latest(df, t).set_index(["ts_code", "end_date"])
            missing = [c for c in cols if c not in got.columns]
            if missing:
                return pd.DataFrame(np.nan, index=cur.index,
                                    columns=[c + suffix for c in cols])
            try:
                picked = got.loc[keys, cols]
            except KeyError:
                picked = got.reindex(keys)[cols]
            picked.index = cur.index
            picked.columns = [c + suffix for c in cols]
            return picked.astype(float)

        panel = cur[["end_date"]].copy()
        # 当期：利润表主体 + 资产负债/现金流主体（同期公告，未公告者自然 NaN）
        panel = panel.join(_join(inc, cur_keys,
                                 ["revenue", "oper_cost", "n_income_attr_p"], ""))
        panel = panel.join(_join(bal, cur_keys,
                                 ["total_assets", "total_liab", "total_hldr_eqy_exc_min_int"], ""))
        panel = panel.join(_join(cf, cur_keys, ["n_cashflow_act"], ""))
        # 同比期：三表同键连 prev_key
        panel = panel.join(_join(inc, prev_keys,
                                 ["revenue", "oper_cost", "n_income_attr_p"], "_prev"))
        panel = panel.join(_join(bal, prev_keys,
                                 ["total_assets", "total_liab", "total_hldr_eqy_exc_min_int"], "_prev"))
        panel = panel.join(_join(cf, prev_keys, ["n_cashflow_act"], "_prev"))

        revenue = panel["revenue"]
        oper_cost = panel["oper_cost"]
        profit = panel["n_income_attr_p"]
        cfo = panel["n_cashflow_act"]
        assets = panel["total_assets"]
        liab = panel["total_liab"]
        equity = panel["total_hldr_eqy_exc_min_int"]

        def _safe_div(a, b):
            return a / b.where(b.abs() > 1e-9)

        gross_margin = _safe_div(revenue - oper_cost, revenue)
        turnover = _safe_div(revenue, assets)
        roe = _safe_div(profit, equity)
        factors = {
            "ocf_to_ni": _safe_div(cfo, profit),
            "accrual_ratio": _safe_div(profit - cfo, assets),
            "gross_margin_chg": gross_margin
                                - _safe_div(panel["revenue_prev"] - panel["oper_cost_prev"],
                                            panel["revenue_prev"]),
            "leverage_chg": _safe_div(liab, assets) - _safe_div(panel["total_liab_prev"],
                                                                panel["total_assets_prev"]),
            "asset_turnover_chg": turnover - _safe_div(panel["revenue_prev"],
                                                       panel["total_assets_prev"]),
            "roe_chg": roe - _safe_div(panel["n_income_attr_p_prev"],
                                       panel["total_hldr_eqy_exc_min_int_prev"]),
        }

        rows = []
        for factor_id, values in factors.items():
            values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
            for ts_code, value in values.dropna().items():
                rows.append({"ts_code": ts_code, "factor_id": factor_id,
                             "trade_date": t, "factor_value": float(value)})
        return pd.DataFrame(rows)

    def compute_and_save(self, trade_date: str, engine=None) -> Dict[str, Any]:
        """单日计算 + 标准化落库（整体替换该日这 6 个因子）。"""
        frame = self.compute_for_date(trade_date)
        if frame.empty:
            return {"error": f"{trade_date} 无可用财务数据"}

        if engine is None:
            engine = self._engine
        if engine is None:
            from app.services.factor_engine import FactorEngine

            engine = FactorEngine()
        result = engine._calculate_factor_stats(frame)
        ok = engine.save_factor_values(result, replace_factor_ids=list(FUNDAMENTAL_PIT_FACTOR_IDS))
        if not ok:
            return {"error": f"{trade_date} 基本面因子落库失败"}
        per_factor = result.groupby("factor_id")["ts_code"].nunique().to_dict()
        return {"trade_date": trade_date, "rows": len(result),
                "stocks_per_factor": per_factor}

    def compute_range(self, start_date: str, end_date: str,
                      engine=None, save: bool = True) -> Dict[str, Any]:
        """区间回填：只落交易日（按交易日历），报表按公告日自然生效。"""
        from app.services.data_reader import ParquetDataReader

        reader = ParquetDataReader(data_dir=self.data_dir)
        calendar = reader.get_trade_calendar()
        if calendar.empty:
            return {"error": "无交易日历"}
        work = calendar.copy()
        work["cal_date"] = pd.to_datetime(work["cal_date"], errors="coerce")
        work["is_open"] = pd.to_numeric(work["is_open"], errors="coerce").fillna(0).astype(int)
        days = work[(work["is_open"] == 1)
                    & (work["cal_date"] >= pd.to_datetime(start_date))
                    & (work["cal_date"] <= pd.to_datetime(end_date))]
        days = [d.strftime("%Y%m%d") for d in days["cal_date"]]

        if engine is None:
            engine = self._engine
        if engine is None:
            from app.services.factor_engine import FactorEngine

            engine = FactorEngine()

        self._load_statements()  # 预热一次
        results = {"days": 0, "rows": 0, "errors": []}
        for day in days:
            frame = self.compute_for_date(day)
            if frame.empty:
                continue
            if save:
                standardized = engine._calculate_factor_stats(frame)
                ok = engine.save_factor_values(
                    standardized, replace_factor_ids=list(FUNDAMENTAL_PIT_FACTOR_IDS))
                if not ok:
                    results["errors"].append(day)
                    continue
            results["days"] += 1
            results["rows"] += len(frame)
        results["message"] = f"基本面 PIT 因子回填 {results['days']} 天 / {results['rows']} 行"
        return results
