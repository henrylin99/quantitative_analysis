"""因子分析层（IC/IR、分层回测、相关性）的回归测试。

用"完美因子"（因子值恰好等于未来收益）做确定性验证：
- IC 必须为 +1；取反后为 -1
- 分层收益应单调、多空价差为正
- 相关性矩阵能识别完全负相关的因子
"""
import pandas as pd
import pytest

from app.services.factor_analyzer import FactorAnalyzer

pytestmark = pytest.mark.module_factor_engine

STOCKS = ["A.SZ", "B.SZ", "C.SZ", "D.SZ"]
DAILY_RETURNS = {"A.SZ": 0.01, "B.SZ": 0.02, "C.SZ": -0.01, "D.SZ": 0.0005}
DATES = pd.date_range("2026-01-05", periods=10, freq="D")


def _build_frames():
    """价格 11 天（多一天保证末日因子有未来收益），因子值 10 天。"""
    price_rows = []
    for code in STOCKS:
        price = 10.0
        for date in pd.date_range("2026-01-05", periods=11, freq="D"):
            price_rows.append({
                "ts_code": code, "trade_date": date, "close": price,
            })
            price *= 1 + DAILY_RETURNS[code]

    # 完美因子：因子值 = 该股票恒定的未来日收益
    perfect_rows = []
    for code in STOCKS:
        for date in DATES:
            perfect_rows.append({
                "ts_code": code, "trade_date": date,
                "factor_id": "perfect", "factor_value": DAILY_RETURNS[code],
                "z_score": DAILY_RETURNS[code],
            })
    reversed_rows = [
        {**row, "factor_id": "reversed", "factor_value": -row["factor_value"]}
        for row in perfect_rows
    ]
    return pd.DataFrame(price_rows), pd.DataFrame(perfect_rows), pd.DataFrame(reversed_rows)


class _FakeFactorRepo:
    def __init__(self, frames):
        self.frames = frames

    def get_values(self, factor_ids=None, trade_date=None, ts_codes=None,
                   start_date=None, end_date=None):
        ids = factor_ids or list(self.frames.keys())
        df = pd.concat(
            [self.frames[f] for f in ids if f in self.frames],
            ignore_index=True,
        )
        if df.empty:
            return df
        td = pd.to_datetime(df["trade_date"])
        if trade_date is not None:
            df = df[td == pd.to_datetime(trade_date)]
        if start_date is not None:
            df = df[td >= pd.to_datetime(start_date)]
        if end_date is not None:
            df = df[td <= pd.to_datetime(end_date)]
        return df


class _FakeReader:
    def __init__(self, prices):
        self.prices = prices

    def get_return_prices(self, ts_codes=None, start_date=None, end_date=None):
        df = self.prices
        td = pd.to_datetime(df["trade_date"])
        if start_date is not None:
            df = df[td >= pd.to_datetime(start_date)]
        if end_date is not None:
            df = df[td <= pd.to_datetime(end_date)]
        return df


def _make_analyzer():
    prices, perfect, reversed_ = _build_frames()
    repo = _FakeFactorRepo({"perfect": perfect, "reversed": reversed_})
    return FactorAnalyzer(factor_repo=repo, data_reader=_FakeReader(prices))


def test_perfect_factor_ic_equals_one():
    result = _make_analyzer().ic_analysis("perfect", forward_period=1, min_stocks=3)

    summary = result["summary"]
    assert summary["n_dates"] == 10
    assert summary["ic_mean"] == pytest.approx(1.0)
    assert summary["ic_positive_ratio"] == pytest.approx(1.0)
    # 完美因子 IC 恒为 1、标准差为 0，ICIR 退化为守卫值 0（非负即可）
    assert summary["ic_ir"] >= 0
    assert len(result["ic_series"]) == 10


def test_reversed_factor_ic_equals_minus_one():
    result = _make_analyzer().ic_analysis("reversed", forward_period=1, min_stocks=3)
    assert result["summary"]["ic_mean"] == pytest.approx(-1.0)


def test_quantile_layering_spread_positive():
    result = _make_analyzer().quantile_analysis(
        "perfect", forward_period=1, n_quantiles=2, min_stocks=3,
    )

    assert result["n_dates"] == 10
    top = result["quantiles"][-1]["mean_forward_return"]
    bottom = result["quantiles"][0]["mean_forward_return"]
    assert top > 0, "高分组（因子值最大）应为正收益"
    assert top > bottom, "完美因子的分层收益必须单调"
    assert result["long_short_spread"] == pytest.approx(top - bottom)
    assert result["long_short_spread_annualized"] == pytest.approx(
        (top - bottom) * 252
    )


def test_correlation_matrix_detects_redundancy():
    result = _make_analyzer().correlation_matrix(
        ["perfect", "reversed"], min_stocks=3,
    )

    assert result["n_dates"] == 10
    matrix = result["matrix"]
    assert matrix["perfect"]["perfect"] == pytest.approx(1.0)
    assert matrix["perfect"]["reversed"] == pytest.approx(-1.0)
    assert matrix["reversed"]["reversed"] == pytest.approx(1.0)


def test_insufficient_stocks_reports_empty_summary():
    result = _make_analyzer().ic_analysis("perfect", forward_period=1, min_stocks=100)

    assert result["summary"]["n_dates"] == 0
    assert result["summary"]["ic_mean"] is None
    assert result["ic_series"] == []
    assert "message" in result


# ----------------------------------------------------------------------
# 分位组合净值回测
# ----------------------------------------------------------------------

def test_quantile_portfolio_backtest_monotone_groups():
    """完美因子：高分组净值 > 低分组，多空净值逐期上行。

    4 只股票分 2 组：G1={C(-1%), D(0.05%)}、G2={A(1%), B(2%)}，
    持有 2 天非重叠调仓。10 个因子日 → 信号日 5 个 → 完整期 4 个。
    """
    result = _make_analyzer().quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4,
    )

    assert result["n_periods"] == 4
    g2 = result["groups_summary"]["g2"]
    g1 = result["groups_summary"]["g1"]
    assert g2["total_return"] > 0
    assert g1["total_return"] < g2["total_return"], "完美因子高分组必须跑赢低分组"
    # 每期多空收益均为正 → 净值单调上行、胜率 1.0
    assert result["nav_long_short"] == sorted(result["nav_long_short"])
    assert result["long_short_summary"]["win_rate"] == 1.0
    # T+1 成交：首个执行日 = 首个信号日的下一交易日
    assert result["periods"][0]["signal_date"] == "2026-01-05"
    assert result["periods"][0]["exec_date"] == "2026-01-06"
    assert result["periods"][0]["next_exec_date"] == "2026-01-08"


def test_quantile_portfolio_backtest_cost_deducted_on_turnover():
    """成本只按换手扣：成员不变时首期建仓全额扣费，此后零换手零费用。"""
    no_cost = _make_analyzer().quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4, cost_bps=0.0,
    )
    with_cost = _make_analyzer().quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4, cost_bps=10.0,
    )

    first_free = no_cost["periods"][0]["g2_return"]
    first_cost = with_cost["periods"][0]["g2_return"]
    # 首期换手 1.0 → 双边费用 2 × 10bps
    assert first_cost == pytest.approx(first_free - 2 * 10 * 1e-4)
    # 成员恒定：后续期换手 0、收益与零费口径一致
    assert with_cost["periods"][1]["g2_turnover"] == 0.0
    assert with_cost["periods"][1]["g2_return"] == pytest.approx(
        no_cost["periods"][1]["g2_return"]
    )
    # 平均换手 = (1 + 0 + 0 + 0) / 4
    assert with_cost["avg_turnover"]["g2"] == pytest.approx(0.25)


def test_quantile_portfolio_backtest_too_short_range():
    result = _make_analyzer().quantile_portfolio_backtest(
        "perfect", start_date="2026-01-05", end_date="2026-01-06",
        holding_days=20, n_quantiles=2, min_stocks=4,
    )
    assert "error" in result


# ----------------------------------------------------------------------
# 5.1 多空增强：等名义本金对冲净值 / 行业中性 / 波动率目标
# ----------------------------------------------------------------------

class _ReaderWithIndustry(_FakeReader):
    def __init__(self, prices, industry):
        super().__init__(prices)
        self._industry = industry

    def get_stock_basic(self):
        return pd.DataFrame(
            [{"ts_code": c, "industry": ind} for c, ind in self._industry.items()]
        )


def test_long_short_hedged_half_spread_and_caveats():
    """等名义本金对冲净值 = spread 的一半敞口（无 vol_target 时杠杆恒 1）。"""
    result = _make_analyzer().quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4,
    )
    assert result["nav_long_short_hedged"] == sorted(result["nav_long_short_hedged"])
    assert result["long_short_hedged_summary"]["win_rate"] == 1.0
    # hedged 期收益 = spread/2 → 累计收益低于全额 spread
    assert result["long_short_hedged_summary"]["total_return"] < \
        result["long_short_summary"]["total_return"]
    assert all(lev == 1.0 for lev in result["long_short_leverage"])
    assert "研究级" in result["ls_caveats"] and "融券" in result["ls_caveats"]
    assert result["industry_neutral"] is False


def test_long_short_industry_neutral_changes_membership():
    """行业中性重排截面：A/B 同业、C/D 同业时，G2 成员从 {A,B} 变为 {B,D}。"""
    prices, perfect, reversed_ = _build_frames()
    repo = _FakeFactorRepo({"perfect": perfect})
    # 原始排名：残差后 D(+0.00525) > B(+0.005) > A(-0.005) > C(-0.00525)
    reader = _ReaderWithIndustry(
        prices, {"A.SZ": "X", "B.SZ": "X", "C.SZ": "Y", "D.SZ": "Y"})
    analyzer = FactorAnalyzer(factor_repo=repo, data_reader=reader)

    result = analyzer.quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4,
        industry_neutral=True,
    )
    assert result["industry_neutral"] is True
    # 中性化后 G2 = {B, D}：日收益 2% 与 0.05% → 高组收益低于原始 {A,B}=1.5%/日
    raw = _make_analyzer().quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4)
    assert result["groups_summary"]["g2"]["annualized_return"] < \
        raw["groups_summary"]["g2"]["annualized_return"]


def test_long_short_vol_target_leverage_capped_and_ex_ante():
    """波动率目标：杠杆只用截至上一期的历史（首期恒 1），且封顶 leverage_cap。"""
    result = _make_analyzer().quantile_portfolio_backtest(
        "perfect", holding_days=2, n_quantiles=2, min_stocks=4,
        vol_target=0.10, leverage_cap=1.5,
    )
    levs = result["long_short_leverage"]
    assert levs[0] == 1.0  # 无历史 → 杠杆 1
    assert all(0 < lev <= 1.5 for lev in levs)
    assert result["vol_target"] == 0.10
    # hedged 收益 = lev × spread / 2（首期 lev=1 与无目标口径一致）
    assert result["nav_long_short_hedged"][0] == pytest.approx(
        _make_analyzer().quantile_portfolio_backtest(
            "perfect", holding_days=2, n_quantiles=2, min_stocks=4,
        )["nav_long_short_hedged"][0]
    )


class _FakeStore:
    """带分区目录的假存储：验证无日期请求被限定到最近两年。"""

    def __init__(self, partitions):
        self.partitions = partitions

    def list_partitions(self, table, by):
        return list(self.partitions)


def _make_analyzer_with_store(partitions):
    analyzer = _make_analyzer()
    analyzer.factor_repo.store = _FakeStore(partitions)
    analyzer.factor_repo.TABLE_VALUES = "factor_values"
    return analyzer


def test_bounded_date_range_defaults_to_last_two_years():
    analyzer = _make_analyzer_with_store(
        ["2024-01-02", "2025-06-30", "2026-09-30"])
    bounds = analyzer._bounded_date_range(None, None)
    assert bounds == ("2024-09-30", "2026-09-30")

    # 显式传入区间原样透传
    assert analyzer._bounded_date_range("2025-01-01", "2025-06-30") == (
        "2025-01-01", "2025-06-30"
    )
    # 只传 start 时 end 补齐为最新分区
    assert analyzer._bounded_date_range("2025-01-01", None) == (
        "2025-01-01", "2026-09-30"
    )


def test_bounded_date_range_empty_library():
    analyzer = _make_analyzer_with_store([])
    assert analyzer._bounded_date_range(None, None) is None


def test_ic_analysis_without_dates_applies_default_bounds():
    """无日期 IC 请求也必须带边界进 get_values（防全库扫描 OOM）。"""
    analyzer = _make_analyzer_with_store(
        [d.strftime("%Y-%m-%d") for d in DATES])
    calls = {}
    original = analyzer.factor_repo.get_values

    def spy(**kwargs):
        calls.update(kwargs)
        return original(**kwargs)

    analyzer.factor_repo.get_values = spy
    result = analyzer.ic_analysis("perfect", forward_period=1, min_stocks=3)
    assert calls["start_date"] is not None
    assert calls["end_date"] is not None
    assert "error" not in result


def test_correlation_without_dates_applies_default_bounds():
    analyzer = _make_analyzer_with_store(
        [d.strftime("%Y-%m-%d") for d in DATES])
    calls = {}
    original = analyzer.factor_repo.get_values

    def spy(**kwargs):
        calls.update(kwargs)
        return original(**kwargs)

    analyzer.factor_repo.get_values = spy
    result = analyzer.correlation_matrix(["perfect", "reversed"], min_stocks=3)
    assert calls["start_date"] is not None
    assert calls["end_date"] is not None
    assert "error" not in result

    # 单日口径（trade_date）不走默认边界
    calls.clear()
    analyzer.correlation_matrix(["perfect", "reversed"],
                                trade_date="2026-01-06", min_stocks=3)
    assert calls.get("start_date") is None
