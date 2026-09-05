"""扶摇数据 → 本项目 Parquet 表（tushare 口径）的归一化层。

所有单位/时区/字段换算集中在这里，下载脚本不做二次换算，
保证 fuyao 与 tushare 产出的同一张表 schema 完全同构：
读取侧（ParquetDataReader 及所有业务服务）对数据源无感知。

对照表（daily 表）：
- ts_code   ← thscode（同为 600000.SH 风格，直传）
- trade_date← date_ms（北京时间零点 epoch ms，北京时区解析）
- open/high/low/close ← open_price/high_price/low_price/close_price（直传）
- vol       ← volume ÷ 100（股 → 手）
- amount    ← turnover ÷ 1000（元 → 千元）
- pre_close ← 按标的分组的前一交易日 close 推导（扶摇日K无此字段）
- change/pct_chg ← close/pre_close 推导

已知局限：pre_close 由前收盘价直接推导，遇除权除息日（前收盘价被交易所
调整）该日 change/pct_chg 会反映原始价差而非真实涨跌幅。需要精确复权口径
的消费者继续使用 tushare stk_factor（含 adj_factor/前复权价）。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from app.utils.data_sources.fuyao_client import beijing_ms_to_ymd

#: daily 表标准列（与 ParquetDataReader.STANDARD_COLUMNS["daily"] 一致）
DAILY_COLUMNS = [
    "ts_code", "trade_date", "open", "high", "low", "close",
    "pre_close", "change", "pct_chg", "vol", "amount",
]

# 扶摇快照字段双命名：实测 vs 官方文档
_SNAPSHOT_NAME_CANDIDATES = {
    "name": ["name"],
    "open": ["open_price"],
    "high": ["high_price", "highest_price"],
    "low": ["low_price", "lowest_price"],
    "prev_close": ["prev_price", "prev_close_price"],
}
_SNAPSHOT_NUMERIC = ("last_price", "open", "high", "low", "prev_close",
                     "price_change", "price_change_ratio_pct", "volume", "turnover")

# 财务三表：扶摇原始字段 → tushare 列名（映射之外的扶摇独有字段原名透传）
INCOME_FIELD_MAP = {
    "operating_income": "revenue",
    "operating_costs": "oper_cost",
    "sales_fee": "sell_exp",
    "manage_fee": "admin_exp",
    "research_and_development_expenses": "rd_exp",
    "operating_profit": "operate_profit",
    "interest_expenses": "fin_exp",
    "profit_total": "total_profit",
    "income_tax_expense": "income_tax",
    "net_profit": "n_income",
    "parent_holder_net_profit": "n_income_attr_p",
    "basic_eps": "basic_eps",
}
BALANCE_FIELD_MAP = {
    "assets_total": "total_assets",
    "total_current_assets": "total_cur_assets",
    "non_current_nets_total": "total_nca",
    "cash": "cash_equivalents",
    "accounts_receivable": "accounts_receiv",
    "total_debt": "total_liab",
    "holder_equity_total": "total_hldr_eqy_exc_min_int",
}
CASHFLOW_FIELD_MAP = {
    "act_cash_flow_net": "n_cashflow_act",
    "invest_cash_flow_net": "n_cashflow_inv_act",
    "financing_cash_flow_net": "n_cash_flows_fnc_act",
    "pay_fixed_assets_etc_cash": "construct_fix_asset",
    "pay_dividends_profits_interest_cash": "assign_dividend_porfit_int",
    "cash_equivalents_net_addition": "n_cash_inc_cash_equi",
}

_FINANCIAL_META_MAP = {
    "thscode": "ts_code",
    "report_date_ms": "ann_date",
    "period_end_ms": "end_date",
    "fiscal_year": "fiscal_year",
    "fiscal_period": "fiscal_period",
}

FINANCIAL_FIELD_MAPS = {
    "income": INCOME_FIELD_MAP,
    "balance_sheet": BALANCE_FIELD_MAP,
    "cash_flow": CASHFLOW_FIELD_MAP,
}


def _first_present(row: Dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def daily_frame_from_dump(dump_df: pd.DataFrame, trade_dates: Iterable[str]) -> pd.DataFrame:
    """全市场日K dump（parquet 已读入）→ tushare 口径 daily DataFrame。

    dump 列：thscode/date_ms/open_price/high_price/low_price/close_price/
    volume/turnover（实测 2026-09，另有 currency/interval/adjusted 常量列）。

    pre_close 在整个 dump 范围内按标的分组推导，再过滤目标交易日，
    因此只要 dump 含目标日期的前一交易日，边界日 pre_close 就是正确的。
    """
    wanted = {str(d) for d in trade_dates}
    if dump_df is None or dump_df.empty or not wanted:
        return pd.DataFrame(columns=DAILY_COLUMNS)

    df = dump_df.copy()
    if "adjusted" in df.columns:
        # 防御：dump 变为复权口径时拒绝落库，而不是静默混入复权价
        df = df[df["adjusted"] == "none"]
    df["trade_date"] = df["date_ms"].map(beijing_ms_to_ymd)
    df = df.rename(columns={
        "thscode": "ts_code",
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
    })
    # 先在整个 dump 范围推导 pre_close（目标日期的前一交易日也在 dump 内），
    # 再过滤目标交易日——先过滤会让边界日的 pre_close 变成 NaN
    frame = _finalize_daily(df)
    frame = frame[frame["trade_date"].isin(wanted)]
    if frame.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    return frame.reset_index(drop=True)


def daily_frame_from_kline_rows(rows: List[Dict[str, Any]], ts_code: str) -> pd.DataFrame:
    """单标的 historical 接口 rows → tushare 口径 daily DataFrame。"""
    if not rows:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    df = pd.DataFrame(rows)
    df["ts_code"] = ts_code
    df["trade_date"] = df["date_ms"].map(beijing_ms_to_ymd)
    df = df.rename(columns={
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
    })
    return _finalize_daily(df)


def _finalize_daily(df: pd.DataFrame) -> pd.DataFrame:
    """列换算 + pre_close/change/pct_chg 推导 + 标准列输出。"""
    df = df.copy()
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 股 → 手（向下取整，与 tick-stock-panel 口径一致）；元 → 千元
    df["vol"] = np.floor(pd.to_numeric(df["volume"], errors="coerce") / 100.0)
    df["amount"] = pd.to_numeric(df["turnover"], errors="coerce") / 1000.0

    df = df.sort_values(["ts_code", "trade_date"], kind="mergesort")
    df["pre_close"] = df.groupby("ts_code", sort=False)["close"].shift(1)
    df["change"] = (df["close"] - df["pre_close"]).round(3)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["pct_chg"] = ((df["close"] / df["pre_close"] - 1.0) * 100.0).round(4)
    df.loc[df["pre_close"].isna(), "change"] = np.nan
    df.loc[df["pre_close"].isna(), "pct_chg"] = np.nan

    # 停牌日（OHLC 全空）过滤，与 tushare daily 不返回停牌日一致
    df = df.dropna(subset=["open", "high", "low", "close"], how="all")

    df["trade_date"] = df["trade_date"].astype(str)
    return df[DAILY_COLUMNS].reset_index(drop=True)


def snapshot_rows_to_quote_frame(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """全市场快照 rows → 行情 DataFrame（供看板/自选聚合）。

    输出列：ts_code/name/last_price/open/high/low/prev_close/change/
    pct_chg/volume(股)/turnover(元)。涨跌幅保持百分数原值。
    """
    records = []
    for row in rows or []:
        ts_code = row.get("thscode")
        if not ts_code:
            continue
        record = {
            "ts_code": ts_code,
            "name": _first_present(row, _SNAPSHOT_NAME_CANDIDATES["name"]),
            "last_price": row.get("last_price"),
            "open": _first_present(row, _SNAPSHOT_NAME_CANDIDATES["open"]),
            "high": _first_present(row, _SNAPSHOT_NAME_CANDIDATES["high"]),
            "low": _first_present(row, _SNAPSHOT_NAME_CANDIDATES["low"]),
            "prev_close": _first_present(row, _SNAPSHOT_NAME_CANDIDATES["prev_close"]),
            "change": row.get("price_change"),
            "pct_chg": row.get("price_change_ratio_pct"),
            "volume": row.get("volume"),
            "turnover": row.get("turnover"),
        }
        for col in _SNAPSHOT_NUMERIC:
            value = record.get(col)
            record[col] = float(value) if value is not None and value == value else None
        records.append(record)
    return pd.DataFrame(records)


def snapshot_rows_to_stock_basic(rows: List[Dict[str, Any]], existing: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """全市场快照 rows → stock_basic 表（代码清单全量对齐）。

    快照没有股票名称字段（同花顺口径名称靠下游维表关联）：已有记录保留
    原值（tushare 产出），仅追加快照中新出现的代码；new 代码 list_status
    记为 L（快照只在市股），name 留空待 tushare 版补齐。
    """
    fresh = pd.DataFrame([
        {
            "ts_code": row.get("thscode"),
            "symbol": str(row.get("thscode", "")).split(".")[0] if row.get("thscode") else None,
            "name": _first_present(row, _SNAPSHOT_NAME_CANDIDATES["name"]),
        }
        for row in rows or []
        if row.get("thscode")
    ])
    fresh = fresh.drop_duplicates(subset="ts_code")
    if existing is None or existing.empty:
        fresh["list_status"] = "L"
        return fresh.reset_index(drop=True)

    base = existing.copy()
    # existing 可能缺 name 列（旧版 stock_basic），补空列保证 merge 后赋值不炸
    if "name" not in base.columns:
        base["name"] = None
    base = base.merge(fresh[["ts_code", "name"]], on="ts_code", how="left", suffixes=("", "_fuyao"))
    base["name"] = base["name_fuyao"].fillna(base["name"])
    base = base.drop(columns=["name_fuyao"])

    known = set(base["ts_code"].astype(str))
    additions = fresh[~fresh["ts_code"].astype(str).isin(known)].copy()
    if not additions.empty:
        for col in base.columns:
            if col not in additions.columns:
                additions[col] = "L" if col == "list_status" else None
        base = pd.concat([base, additions[base.columns]], ignore_index=True)
    return base.reset_index(drop=True)


def financial_items_to_frame(
    items: List[Dict[str, Any]],
    table: str,
    ts_code: str,
) -> pd.DataFrame:
    """单标的财务报表 items → tushare 兼容 DataFrame。

    - 元数据：thscode→ts_code、report_date_ms→ann_date、period_end_ms→end_date
      （ms 字段同样按北京时区解析）
    - 字段映射表内的列改为 tushare 列名；映射表之外的扶摇独有字段原名透传
    - null 保持 NaN（= 未披露），不伪造 0
    """
    field_map = FINANCIAL_FIELD_MAPS.get(table)
    if field_map is None:
        raise ValueError(f"未知财务表: {table}")
    records: List[Dict[str, Any]] = []
    for item in items or []:
        record: Dict[str, Any] = {}
        for src, dst in _FINANCIAL_META_MAP.items():
            if src in item:
                value = item[src]
                if dst in ("ann_date", "end_date"):
                    value = beijing_ms_to_ymd(value)
                record[dst] = value
        for src, dst in field_map.items():
            if src in item:
                record[dst] = item[src]
        for src, value in item.items():
            if src not in field_map and src not in _FINANCIAL_META_MAP:
                record[src] = value
        records.append(record)
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["ts_code"] = ts_code
        frame["end_date"] = frame["end_date"].astype(str)
        if "ann_date" in frame.columns:
            frame["ann_date"] = frame["ann_date"].astype(str)
    return frame
