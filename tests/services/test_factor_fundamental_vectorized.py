"""基本面/估值分位因子向量化的等价性测试。

向量化实现（groupby-rolling + merge_asof + rolling.rank）必须与旧
逐股 Python 循环 / scipy percentileofscore 逐窗口回调在真实口径下
产出完全一致——这里用覆盖边界情况的合成财务数据对照两套实现。
"""
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.services.factor_engine import FactorEngine

pytestmark = pytest.mark.module_factor_engine


# ---------------------------------------------------------------------------
# 旧逐股循环参考实现（性能优化前的事实口径，平移自 git 历史）
# ---------------------------------------------------------------------------

def _ref_ttm_level_factor(engine, data, factor_id, income_col, balance_col):
    if data.get("income") is None or data["income"].empty:
        return pd.DataFrame()
    income_df = engine._prepare_quarterly_reports(data["income"], [income_col])
    if income_df.empty or income_col not in income_df.columns:
        return pd.DataFrame()

    balance_df = None
    if data.get("balance") is not None and not data["balance"].empty:
        balance_df = engine._prepare_quarterly_reports(data["balance"], [balance_col])

    results = []
    for ts_code, inc in income_df.groupby("ts_code", sort=False):
        bal = None
        if balance_df is not None and not balance_df.empty:
            bal = balance_df[balance_df["ts_code"] == ts_code].reset_index(drop=True)
            if bal.empty:
                continue
        for i in range(3, len(inc)):
            window = inc.iloc[i - 3:i + 1]
            if window[income_col].isna().any():
                continue
            ttm = float(window[income_col].sum())
            cur_end = inc.iloc[i]["end_date"]
            if bal is None or len(bal) == 0:
                continue
            b_window = bal[bal["end_date"] <= cur_end].tail(2)
            if len(b_window) < 2 or b_window[balance_col].isna().any():
                continue
            avg_denom = float(b_window[balance_col].mean())
            if avg_denom <= 0:
                continue
            stamp = engine._snapshot_stamp(
                list(window.itertuples()) + list(b_window.itertuples())
            )
            if stamp is None:
                continue
            results.append({
                "ts_code": ts_code, "trade_date": stamp,
                "factor_value": ttm / avg_denom,
            })
    if not results:
        return pd.DataFrame()
    result = pd.DataFrame(results)
    result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    result["factor_id"] = factor_id
    return result[["ts_code", "trade_date", "factor_id", "factor_value"]]


def _ref_yoy_ttm_growth_factor(engine, data, factor_id, income_col):
    if data.get("income") is None or data["income"].empty:
        return pd.DataFrame()
    income_df = engine._prepare_quarterly_reports(data["income"], [income_col])
    if income_df.empty or income_col not in income_df.columns:
        return pd.DataFrame()

    results = []
    for ts_code, inc in income_df.groupby("ts_code", sort=False):
        for i in range(7, len(inc)):
            current = inc.iloc[i - 3:i + 1]
            previous = inc.iloc[i - 7:i - 3]
            if current[income_col].isna().any() or previous[income_col].isna().any():
                continue
            prev_ttm = float(previous[income_col].sum())
            if prev_ttm <= 0:
                continue
            growth = (float(current[income_col].sum()) - prev_ttm) / prev_ttm
            stamp = engine._snapshot_stamp(list(current.itertuples()))
            if stamp is None:
                continue
            results.append({
                "ts_code": ts_code, "trade_date": stamp, "factor_value": growth,
            })
    if not results:
        return pd.DataFrame()
    result = pd.DataFrame(results)
    result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    result["factor_id"] = factor_id
    return result[["ts_code", "trade_date", "factor_id", "factor_value"]]


# ---------------------------------------------------------------------------
# 合成财务数据：覆盖公告日孰晚/缺失/周末、季报缺口、NaN 值、
# 非正分母、无负债表股票、同日公告去重等边界
# ---------------------------------------------------------------------------

QUARTER_ENDS = [
    "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
    "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
    "2026-03-31", "2026-06-30",
]


def _report_rows(ts_code, quarters, values, ann_dates):
    rows = []
    for end, value, ann in zip(quarters, values, ann_dates):
        row = {
            "ts_code": ts_code,
            "end_date": end,
            "n_income_attr_p": value,
            "revenue": value * 10 if value is not None else None,
        }
        if isinstance(ann, tuple):
            row["ann_date"], row["f_ann_date"] = ann
        elif ann is not None:
            row["ann_date"] = ann
        rows.append(row)
    return rows


def _make_fundamental_data():
    # 股票 A：10 个季度完整，含一个 NaN 季、一个缺失公告日（退回
    # end_date）、一个 f_ann_date 晚于 ann_date、年报与一季报同日公告
    ann_a = [
        "20240420",                 # Q1'24
        ("20240713", "20240720"),   # Q2'24：周六公告 + f_ann 更晚（孰晚口径）
        "20241026",                 # Q3'24
        "20250329",                 # Q4'24（周六）
        None,                       # Q1'25：公告日缺失 → 退回 end_date
        "20250822",                 # Q2'25
        "20251025",                 # Q3'25（周六）
        "20260427",                 # Q4'25：与 Q1'26 同日公告 → 去重留新
        "20260427",                 # Q1'26
        "20260820",                 # Q2'26
    ]
    values_a = [10.0, 12.0, np.nan, 14.0, 15.0, 16.0, 13.0, 17.0, 18.0, 19.0]
    income = _report_rows("000001.SZ", QUARTER_ENDS, values_a, ann_a)

    # 股票 B：缺 2024Q3 行（非日历连续的「连续 4 条记录」语义）
    quarters_b = [q for q in QUARTER_ENDS if q != "2024-09-30"]
    values_b = [5.0, 6.0, 7.0, 6.0, 5.0, 4.0, 5.0, 6.0, 7.0]
    ann_b = ["20240422", "20240722", "20250420", "20250820",
             "20251024", "20260425", "20260426", "20260821", "20260822"]
    income += _report_rows("600000.SH", quarters_b, values_b, ann_b)

    # 股票 C：只有利润表（无负债表）——roe/roa 必须排除，growth 正常
    values_c = [3.0, 4.0, 5.0, 4.0, 5.0, 6.0, 7.0, 6.0, 7.0, 8.0]
    income += _report_rows("300750.SZ", QUARTER_ENDS, values_c,
                           [None] * 10)

    # 资产负债表：A 完整（含一个 NaN、一段非正值），B 仅 1 行（不足 2 条），
    # C 缺席
    balance = []
    balance_assets_a = [100.0, 110.0, np.nan, 120.0, 130.0, 125.0, 128.0,
                        140.0, 150.0, 155.0]
    for end, ta, ann in zip(QUARTER_ENDS, balance_assets_a, ann_a):
        row = {"ts_code": "000001.SZ", "end_date": end,
               "total_assets": ta, "total_hldr_eqy_exc_min_int": ta * 0.5}
        if isinstance(ann, tuple):
            row["ann_date"], row["f_ann_date"] = ann
        elif ann is not None:
            row["ann_date"] = ann
        balance.append(row)
    balance.append({"ts_code": "600000.SH", "end_date": "2024-06-30",
                    "ann_date": "20240722", "total_assets": 200.0,
                    "total_hldr_eqy_exc_min_int": 80.0})

    return {
        "income": pd.DataFrame(income),
        "balance": pd.DataFrame(balance),
    }


def _sorted(frame):
    return frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


@pytest.mark.parametrize("factor_call,income_col,balance_col,ref", [
    ("_roe_factor", None, None, lambda e, d, fid: _ref_ttm_level_factor(
        e, d, fid, "n_income_attr_p", "total_hldr_eqy_exc_min_int")),
    ("_roa_factor", None, None, lambda e, d, fid: _ref_ttm_level_factor(
        e, d, fid, "n_income_attr_p", "total_assets")),
    ("_revenue_growth_factor", None, None, lambda e, d, fid: _ref_yoy_ttm_growth_factor(
        e, d, fid, "revenue")),
    ("_profit_growth_factor", None, None, lambda e, d, fid: _ref_yoy_ttm_growth_factor(
        e, d, fid, "n_income_attr_p")),
])
def test_fundamental_vectorized_matches_reference(factor_call, income_col,
                                                  balance_col, ref):
    engine = FactorEngine()
    data = _make_fundamental_data()

    new = _sorted(getattr(engine, factor_call)(data, "factor_x"))
    old = _sorted(ref(engine, data, "factor_x"))

    assert len(new) > 0, "合成数据必须产出非空结果，否则等价性无从谈起"
    # 股票 B 负债表不足 2 条：TTM 水平因子必须排除它；growth 因子包含它
    has_b = "600000.SH" in set(new["ts_code"])
    if factor_call in ("_roe_factor", "_roa_factor"):
        assert not has_b
        assert "300750.SZ" not in set(new["ts_code"]), "无负债表股票不得产出 ROE/ROA"
    else:
        assert has_b and "300750.SZ" in set(new["ts_code"])

    pd.testing.assert_frame_equal(
        new, old, check_dtype=False, check_exact=False, rtol=1e-12,
    )


def test_valuation_percentile_matches_scipy_reference():
    engine = FactorEngine()
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-02", periods=60)
    rows = []
    for code, base in (("000001.SZ", 10.0), ("600000.SH", 30.0)):
        values = np.round(base + rng.normal(0, 2, len(dates)), 2)  # 含并列值
        values[3] = values[10]  # 制造并列，检验平均名次口径
        for d, v in zip(dates, values):
            rows.append({"ts_code": code, "trade_date": d, "pe_ttm": v,
                         "pb": v / 5, "ps_ttm": v / 2})
    daily_basic = pd.DataFrame(rows)

    result = engine._pe_percentile_factor({"daily_basic": daily_basic}, "pe_percentile")

    df = daily_basic.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["pe_ttm"] = pd.to_numeric(df["pe_ttm"], errors="coerce")
    df = df[df["pe_ttm"].notna() & (df["pe_ttm"] > 0)]
    valid_counts = df.groupby("ts_code")["pe_ttm"].transform("size")
    df = df[valid_counts > 20].sort_values(["ts_code", "trade_date"])
    expected = df.groupby("ts_code")["pe_ttm"].transform(
        lambda s: s.rolling(252, min_periods=20).apply(
            lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
        )
    )
    ref = pd.DataFrame({
        "ts_code": df["ts_code"], "trade_date": df["trade_date"],
        "factor_value": expected,
    }).dropna(subset=["factor_value"])

    merged = result.merge(ref, on=["ts_code", "trade_date"], suffixes=("_new", "_ref"))
    assert len(merged) == len(ref) == len(result), "行集必须完全一致"
    assert np.allclose(merged["factor_value_new"], merged["factor_value_ref"],
                       rtol=1e-12, atol=1e-12)


def test_snap_to_trade_dates_matches_scalar_version():
    engine = FactorEngine()
    samples = pd.Series(pd.to_datetime([
        "2024-07-13",   # 周六 → 对齐下周一
        "2024-07-15",   # 交易日原样
        "2005-01-01",   # 早于日历覆盖 → 保留原值
        "2099-12-31",   # 晚于日历覆盖 → 保留原值
        "2026-04-27",
    ]))

    vectorized = engine._snap_to_trade_dates(samples)
    for ts, vec in zip(samples, vectorized):
        scalar = engine._snap_to_trade_date(str(ts.date()))
        assert vec == scalar, f"{ts}: 向量化 {vec} 与单值 {scalar} 不一致"


def test_prepare_quarterly_reports_keeps_missing_report_type():
    """fuyao 财务源行不带 report_type（NaN）——须按累计合并口径保留，
    只有显式的 2/4 等单季/调整表才剔除。"""
    engine = FactorEngine()
    frame = pd.DataFrame([
        {"ts_code": "000001.SZ", "end_date": "2026-03-31", "n_income_attr_p": 1.0,
         "ann_date": "20260425"},                                   # fuyao：NaN
        {"ts_code": "000001.SZ", "end_date": "2026-06-30", "n_income_attr_p": 2.0,
         "ann_date": "20260825", "report_type": "2"},               # 单季表：剔除
        {"ts_code": "000001.SZ", "end_date": "2026-06-30", "n_income_attr_p": 2.5,
         "ann_date": "20260824", "report_type": "1"},               # 合并累计：保留
        {"ts_code": "000001.SZ", "end_date": "2026-09-30", "n_income_attr_p": 3.0,
         "ann_date": None, "report_type": None},                    # fuyao：NaN 保留
    ])

    out = engine._prepare_quarterly_reports(frame, ["n_income_attr_p"])

    kept = set(out["end_date"].dt.strftime("%Y-%m-%d"))
    assert kept == {"2026-03-31", "2026-06-30", "2026-09-30"}, (
        "report_type 缺失应按 1 保留，仅显式 2/4 等被剔除"
    )
    # 同一报告期多版本：保留公告日更新的 1 号版本
    q2 = out[out["end_date"] == pd.Timestamp("2026-06-30")]
    assert float(q2["n_income_attr_p"].iloc[0]) == 2.5
