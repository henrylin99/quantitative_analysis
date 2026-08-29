"""回测引擎现金约束 / 调仓带宽 / 除权除息调整的回归测试。

覆盖 2026-08 第二轮修复:
- 买入受可用现金约束（现金不允许为负，此前跌停卖不掉时新买入会打出负现金）
- min_trade_weight 调仓带宽真正生效（此前只在前端展示）
- 涨停允许减仓、跌停禁止减仓
- total_trades 统计实际成交股票次数（此前误用日收益观测点数）
- 拆股/分红日净值不再出现幻影跳变（估值层换后复权口径）
- 信号日处理失败在结果中显式暴露，不再静默缩短回测
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.backtest_engine import BacktestEngine

pytestmark = pytest.mark.module_backtest


def _make_reader(dates, price_map, pct_map, hfq_map=None):
    daily_df = pd.DataFrame(
        [
            {
                "ts_code": code,
                "trade_date": d,
                "close": price_map[code][i],
                "pre_close": price_map[code][max(i - 1, 0)],
                "pct_chg": pct_map[code][i],
            }
            for i, d in enumerate(dates)
            for code in price_map
            if price_map[code][i] is not None
        ]
    )

    def get_daily(ts_codes=None, start_date=None, end_date=None):
        df = daily_df
        if ts_codes is not None:
            df = df[df["ts_code"].isin(ts_codes)]
        if start_date:
            df = df[df["trade_date"] >= start_date]
        if end_date:
            df = df[df["trade_date"] <= end_date]
        return df

    def get_stk_factor(ts_codes=None, start_date=None, end_date=None):
        if not hfq_map:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {"ts_code": code, "trade_date": d, "close_hfq": hfq_map[code][i]}
                for i, d in enumerate(dates)
                for code in hfq_map
            ]
        )

    reader = MagicMock()
    reader.get_trade_dates.return_value = dates
    reader.get_daily.side_effect = get_daily
    reader.get_stk_factor.side_effect = get_stk_factor
    reader.get_stock_basic.return_value = pd.DataFrame(
        [{"ts_code": c, "name": c, "industry": "X"} for c in price_map]
    )
    return reader


def _build_engine(dates, price_map, pct_map, selected_codes, hfq_map=None):
    engine = BacktestEngine()
    engine.backtest_repo = MagicMock()
    engine.backtest_repo.create_run.return_value = {"id": 1}
    engine.data_reader = _make_reader(dates, price_map, pct_map, hfq_map=hfq_map)
    engine._get_stock_selection = lambda cfg, d: [
        {"ts_code": c, "composite_score": 1.0} for c in selected_codes
    ]
    return engine


CFG = {
    "selection_method": "factor_based",
    "top_n": 5,
    "commission_rate": 0.0,
    "slippage_rate": 0.0,
    "stamp_duty_rate": 0.0,
    "optimization": {"method": "equal_weight"},
}


def test_buy_capped_by_available_cash():
    """跌停持仓卖不掉时，新买入必须受现金约束，现金不允许为负。

    旧实现按目标权重直接定仓：A 跌停卖不掉（9 万留在账上），B 仍按
    0.9×14 万买入 12.6 万 → 现金 -7 万（隐性杠杆）。
    """
    engine = BacktestEngine()
    positions = {"A.SZ": 10000}  # 10000×9 = 9 万，跌停无法卖出
    cash = 50_000.0
    total_value = 140_000.0
    prices = {"A.SZ": 9.0, "B.SZ": 100.0}
    tradability = {
        "A.SZ": {"can_buy": True, "can_sell": False},
        "B.SZ": {"can_buy": True, "can_sell": True},
    }

    new_positions, new_cash, _, _, n_trades = engine._rebalance_portfolio(
        positions, cash, {"B.SZ": 0.9}, prices, tradability, total_value,
        commission_rate=0.0, slippage_rate=0.0, stamp_duty_rate=0.0,
    )

    assert new_cash >= -1e-6, f"现金出现负数（隐性杠杆）: {new_cash}"
    assert new_positions["A.SZ"] == 10000, "跌停持仓必须保留"
    # 5 万现金最多买 500 股 B（100 元/股）
    assert new_positions["B.SZ"] == 500
    assert n_trades == 1


def test_min_trade_weight_suppresses_dust_trades():
    """调仓带宽：目标与当前持仓偏差小于阈值时不交易。"""
    engine = BacktestEngine()
    positions = {"A.SZ": 95000}  # 95000×10 = 950000
    cash = 50_000.0
    total_value = 1_000_000.0
    prices = {"A.SZ": 10.0}
    target = {"A.SZ": 0.955}  # 目标 95500 股，偏差 5000/1000000 = 0.5%

    new_positions, new_cash, turnover, _, n_trades = engine._rebalance_portfolio(
        positions, cash, target, prices, {}, total_value,
        commission_rate=0.0, slippage_rate=0.0, stamp_duty_rate=0.0,
        min_trade_weight=0.05,
    )
    assert new_positions == {"A.SZ": 95000}, "带宽内微幅漂移不应触发交易"
    assert turnover == 0
    assert n_trades == 0
    assert new_cash == pytest.approx(50_000.0)

    # 关闭带宽后正常调仓
    new_positions, new_cash, _, _, n_trades = engine._rebalance_portfolio(
        positions, cash, target, prices, {}, total_value,
        commission_rate=0.0, slippage_rate=0.0, stamp_duty_rate=0.0,
        min_trade_weight=0.0,
    )
    assert new_positions == {"A.SZ": 95500}
    assert new_cash == pytest.approx(45_000.0)
    assert n_trades == 1


def test_limit_up_allows_reduction_but_blocks_increase():
    """涨停日不能加仓，但允许减仓/清仓（卖出不受涨停限制）。"""
    engine = BacktestEngine()
    positions = {"A.SZ": 1000}  # 1000×11 = 11000
    prices = {"A.SZ": 11.0}
    tradability = {"A.SZ": {"can_buy": False, "can_sell": True}}
    target = {"A.SZ": 0.5}  # 目标 5500 元 → 500 股

    new_positions, new_cash, _, _, n_trades = engine._rebalance_portfolio(
        positions, 0.0, target, prices, tradability, 11_000.0,
        commission_rate=0.0, slippage_rate=0.0, stamp_duty_rate=0.0,
    )
    assert new_positions == {"A.SZ": 500}, "涨停日应允许减仓到目标"
    assert new_cash == pytest.approx(5500.0)
    assert n_trades == 1


def test_limit_down_blocks_reduction():
    """跌停日目标减仓无法成交，维持原持仓。"""
    engine = BacktestEngine()
    positions = {"A.SZ": 1000}
    prices = {"A.SZ": 9.0}
    tradability = {"A.SZ": {"can_buy": True, "can_sell": False}}
    target = {"A.SZ": 0.5}

    new_positions, _, _, _, _ = engine._rebalance_portfolio(
        positions, 0.0, target, prices, tradability, 9_000.0,
        commission_rate=0.0, slippage_rate=0.0, stamp_duty_rate=0.0,
    )
    assert new_positions == {"A.SZ": 1000}, "跌停日的减仓不能成交，持仓应保留"


def test_total_trades_counts_actual_trades():
    """total_trades 必须是实际发生股份变动的股票次数。

    场景：5 个交易日，D2 买入 A（1 笔），D3 调仓卖出半仓 A + 买入 B
    （2 笔），D4/D5 无变动。合计 3 笔，而日收益观测点有 4 个——
    旧实现把后者当 total_trades。
    """
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10.0] * 5, "B.SZ": [20.0] * 5},
        {"A.SZ": [0] * 5, "B.SZ": [0] * 5},
        ["A.SZ"],
    )

    def selection(cfg, d):
        codes = ["A.SZ"] if d == dates[0] else ["A.SZ", "B.SZ"]
        return [{"ts_code": c, "composite_score": 1.0} for c in codes]

    engine._get_stock_selection = selection
    result = engine.run_backtest(CFG, dates[0], dates[-1], 1_000_000.0, "daily")
    assert result["performance_metrics"]["total_trades"] == 3
    assert len(result["daily_returns"]) == 4


def test_split_adjusted_nav_no_phantom_crash():
    """10送10 拆股日：真实价腰斩但后复权价连续，净值不得跳水。

    旧实现按不复权价估值，拆股日净值会假摔约 50%。
    """
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10.0, 10.0, 5.0, 5.0, 5.0]},   # 真实价：D3 起 1 拆 2
        {"A.SZ": [0, 0, -50.0, 0, 0]},
        ["A.SZ"],
        hfq_map={"A.SZ": [10.0] * 5},              # 后复权价连续
    )
    result = engine.run_backtest(CFG, dates[0], dates[-1], 1_000_000.0, "daily")
    values = [v["total_value"] for v in result["portfolio_values"]]
    # D2 起满仓（100000 股 × 复权价 10 = 100 万），拆股日后净值应保持在 100 万附近
    for date, v in zip(dates[1:], values[1:]):
        assert v > 990_000, f"{date} 净值异常跳水: {v}"
    assert values[0] == pytest.approx(1_000_000.0)


def test_failed_signal_dates_exposed():
    """信号日处理失败必须显式暴露，不能静默缩短回测。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10.0] * 4},
        {"A.SZ": [0] * 4},
        ["A.SZ"],
    )

    def selection(cfg, d):
        if d == dates[1]:
            raise RuntimeError("boom")
        return [{"ts_code": "A.SZ", "composite_score": 1.0}]

    engine._get_stock_selection = selection
    result = engine.run_backtest(CFG, dates[0], dates[-1], 1_000_000.0, "daily")
    assert result["failed_signal_dates"] == [dates[1]]


def test_run_backtest_with_existing_run_id_reuses_record():
    """传入 run_id 时复用已有回测记录（异步任务路径），不再新建。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10.0] * 4},
        {"A.SZ": [0] * 4},
        ["A.SZ"],
    )
    engine.backtest_repo.get_run.return_value = {"id": 42}

    result = engine.run_backtest(CFG, dates[0], dates[-1], 1_000_000.0, "daily", run_id=42)

    engine.backtest_repo.create_run.assert_not_called()
    engine.backtest_repo.update_summary.assert_called_once()
    assert engine.backtest_repo.update_summary.call_args[0][0] == 42
    assert result["run_id"] == 42
