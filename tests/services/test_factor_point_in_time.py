"""因子引擎 point-in-time 语义的回归测试。

覆盖 2026-08 修复的问题:
- 财务因子用公告日 ann_date 打点（end_date 会导致回测提前"看到"业绩）
- 截面 z-score/rank 按交易日分组（跨日期池化会泄漏未来分布）
"""
import pandas as pd
import pytest

from app.services.factor_engine import FactorEngine


@pytest.fixture
def engine():
    return FactorEngine()


def test_point_in_time_stamp_prefers_announcement_date(engine):
    income_row = {"end_date": "20231231", "ann_date": "20240330", "f_ann_date": "20240328"}
    # ann_date 与 f_ann_date 不一致时取孰晚（更保守的 point-in-time 假设）；
    # 输出统一归一化为 YYYY-MM-DD（本地数据 YYYYMMDD/YYYY-MM-DD 混存，
    # 字符串直接比较在混合格式下不可靠）
    assert engine._point_in_time_stamp(income_row) == "2024-03-30"

    # ann_date 缺失时退回 end_date
    only_end = {"end_date": "20231231"}
    assert engine._point_in_time_stamp(only_end) == "2023-12-31"

    # 多张报表取最晚公告日
    balance_row = {"end_date": "20231231", "ann_date": "20240415", "f_ann_date": None}
    income_row2 = {"end_date": "20231231", "ann_date": "20240330", "f_ann_date": None}
    assert engine._point_in_time_stamp(income_row2, balance_row) == "2024-04-15"


def test_roe_factor_stamped_with_ann_date_not_end_date(engine):
    """ROE 打点必须是公告日：end_date=1231 的年报实际 3 个月后才可见。"""
    income = pd.DataFrame(
        [
            # 每股 4 期报告期，最新期 end_date=20231231 但 20240430 才公告
            {"ts_code": "000001.SZ", "end_date": "20231231", "ann_date": "20240430", "n_income_attr_p": 5.0},
            {"ts_code": "000001.SZ", "end_date": "20230930", "ann_date": "20231028", "n_income_attr_p": 5.0},
            {"ts_code": "000001.SZ", "end_date": "20230630", "ann_date": "20230829", "n_income_attr_p": 5.0},
            {"ts_code": "000001.SZ", "end_date": "20230331", "ann_date": "20230427", "n_income_attr_p": 5.0},
        ]
    )
    balance = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "end_date": "20231231", "ann_date": "20240430", "total_hldr_eqy_exc_min_int": 100.0},
            {"ts_code": "000001.SZ", "end_date": "20230930", "ann_date": "20231028", "total_hldr_eqy_exc_min_int": 100.0},
        ]
    )
    result = engine._roe_factor({"income": income, "balance": balance}, "roe_ttm")
    assert not result.empty
    stamped_date = str(result.iloc[0]["trade_date"])
    assert stamped_date.startswith("2024"), f"应以公告日打点， got {stamped_date}"
    assert "20231231" not in stamped_date[:8] or stamped_date >= "20240430"


def test_cross_sectional_stats_grouped_by_trade_date(engine):
    """同一天内的 z-score 只由当天截面决定，不能混入其他日期的分布。"""
    df = pd.DataFrame(
        {
            "ts_code": ["A", "B"] * 2 + ["C", "D"],
            "trade_date": ["2026-01-05"] * 2 + ["2026-02-05"] * 2 + ["2026-01-05"] * 2,
            "factor_id": ["f1"] * 6,
            # 1月截面: 1,2,9,10 (跨日池化会改变均值/方差); 2月截面: 5,6
            "factor_value": [1.0, 2.0, 5.0, 6.0, 9.0, 10.0],
        }
    )
    result = engine._calculate_factor_stats(df)

    jan = result[result["trade_date"] == "2026-01-05"].sort_values("factor_value")
    # 1月截面均值 = 5.5, std(ddof=1) = sqrt((4.5²+3.5²+3.5²+4.5²)/3) = sqrt(65/3) ≈ 4.6547
    jan_std = jan["factor_value"].std(ddof=1)
    assert jan.iloc[0]["z_score"] == pytest.approx((1.0 - 5.5) / jan_std)
    feb = result[result["trade_date"] == "2026-02-05"].sort_values("factor_value")
    # 2月截面只有两个点 5/6：z = ∓1/√2（样本std）。关键是它与跨日期池化的
    # 结果（std≈3.62 → z≈-0.14）明显不同，证明分组生效
    feb_std = feb["factor_value"].std(ddof=1)
    assert feb.iloc[0]["z_score"] == pytest.approx((5.0 - 5.5) / feb_std)
    assert feb.iloc[1]["z_score"] == pytest.approx((6.0 - 5.5) / feb_std)
    pooled_std = df["factor_value"].std(ddof=1)
    assert feb.iloc[0]["z_score"] != pytest.approx((5.0 - df["factor_value"].mean()) / pooled_std, abs=0.05)


def test_stats_columns_always_present(engine):
    """单一数据点也应有统计列（NaN），避免不同批次 concat 时 schema 漂移。"""
    df = pd.DataFrame(
        {"ts_code": ["A"], "trade_date": ["2026-01-05"], "factor_id": ["f1"], "factor_value": [1.0]}
    )
    result = engine._calculate_factor_stats(df)
    assert "percentile_rank" in result.columns
    assert "z_score" in result.columns
