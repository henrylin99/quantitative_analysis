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
