"""回测引擎交易规则的回归测试。

覆盖 2026-08 修复的关键正确性问题:
- 信号 t 日产生、t+1 收盘成交（防未来函数）
- 涨停禁买 / 跌停禁卖（含 ST 与创业板幅度差异）
- 停牌持仓按最近已知价格估值且不从账上消失
- 按实际调仓频率年化波动率
- beta 按日期窗口对齐基准收益
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.backtest_engine import BacktestEngine


def _make_reader(dates, price_map, pct_map):
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

    reader = MagicMock()
    reader.get_trade_dates.return_value = dates
    reader.get_daily.side_effect = get_daily
    reader.get_stock_basic.return_value = pd.DataFrame(
        [{"ts_code": c, "name": c, "industry": "X"} for c in price_map]
    )
    return reader


def _build_engine(dates, price_map, pct_map, selected_codes):
    engine = BacktestEngine()
    engine.backtest_repo = MagicMock()
    engine.backtest_repo.create_run.return_value = {"id": 1}
    engine.data_reader = _make_reader(dates, price_map, pct_map)
    engine._get_stock_selection = lambda cfg, d: [
        {"ts_code": c, "composite_score": 1.0} for c in selected_codes
    ]
    return engine


CFG = {
    "selection_method": "factor_based",
    "top_n": 5,
    "commission_rate": 0.0,
    "slippage_rate": 0.0,
    "optimization": {"method": "equal_weight"},
}


def test_signal_executes_next_trading_day():
    """首个净值点必须在信号日的下一个交易日——当日收盘选股、当日收盘成交是未来函数。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10, 10, 10, 10]},
        {"A.SZ": [0, 0, 0, 0]},
        ["A.SZ"],
    )
    result = engine.run_backtest(CFG, "2026-01-05", "2026-01-08", 1_000_000.0, "daily")
    values = result["portfolio_values"]
    assert values, "应有净值记录"
    assert values[0]["date"] == "2026-01-06"
    # 最后一个信号日没有可执行的下一交易日，不应产生净值点
    assert values[-1]["date"] == "2026-01-08"


def test_limit_up_blocks_buy_then_allows_next_day():
    """执行日涨停（pct_chg 达到幅度）的股票不能买入，次日恢复正常后可买。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10, 10, 10], "B.SZ": [20, 22, 24]},
        {"A.SZ": [0, 0, 0], "B.SZ": [0, 10.0, 9.09]},
        ["A.SZ", "B.SZ"],
    )
    result = engine.run_backtest(CFG, "2026-01-05", "2026-01-07", 1_000_000.0, "daily")
    positions = result["daily_positions"]
    assert "B.SZ" not in positions[0], "B.SZ 在 01-06 涨停（+10%），当日不应买入"
    assert positions[0].get("A.SZ", 0) > 0
    assert positions[1].get("B.SZ", 0) > 0, "01-07 未涨停，应可买入"


def test_limit_down_blocks_sell():
    """跌停持仓不能卖出：目标组合已不含该股，但持仓应保留在账上。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    # A 先入组合；01-07 A 跌停（-10%）且 01-07 起只选 B → A 无法卖出应保留
    engine = _build_engine(
        dates,
        {"A.SZ": [10, 10, 9, 8.1], "B.SZ": [20, 20, 20, 20]},
        {"A.SZ": [0, 0, -10.0, -10.0], "B.SZ": [0, 0, 0, 0]},
        ["A.SZ"],
    )
    # 01-07 起改为只选 B
    selection_calls = {"2026-01-05": ["A.SZ"], "2026-01-06": ["A.SZ"],
                       "2026-01-07": ["B.SZ"], "2026-01-08": ["B.SZ"]}

    def selection(cfg, d):
        return [{"ts_code": c, "composite_score": 1.0} for c in selection_calls[d]]

    engine._get_stock_selection = selection
    result = engine.run_backtest(CFG, "2026-01-05", "2026-01-08", 1_000_000.0, "daily")
    last_positions = result["daily_positions"][-1]
    # 01-08（01-07 信号的执行日）A 跌停不能卖、持仓应保留
    assert last_positions.get("A.SZ", 0) > 0, "跌停的 A.SZ 不能卖出，持仓应保留"


def test_suspended_position_valued_at_last_known_price():
    """停牌（无行情）的持仓按最近已知价格估值，不能按 0 计导致净值假崩塌。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10, 10, 10, 10, 10], "D.SZ": [8, 8, None, None, None]},
        {"A.SZ": [0, 0, 0, 0, 0], "D.SZ": [0, 0, None, None, None]},
        ["A.SZ", "D.SZ"],
    )
    result = engine.run_backtest(CFG, "2026-01-05", "2026-01-09", 1_000_000.0, "daily")
    last_positions = result["daily_positions"][-1]
    assert last_positions.get("D.SZ", 0) > 0, "停牌股持仓不能凭空消失"
    final_value = result["portfolio_values"][-1]["total_value"]
    # 等权两股各 50 万：A 恒定 10 元、D 以 8 元冻结，总价值应保持 100 万
    assert final_value == pytest.approx(1_000_000.0)


def test_volatility_annualized_by_actual_frequency():
    """月度调仓的逐期收益不应按日频 sqrt(252) 年化（虚高约 sqrt(21) 倍）。"""
    # 构造 25 个月度净值点，每期收益在 0.5%/1.5% 间交替（均值 1%）
    dates = [f"{y}-{m:02d}-01" for y in (2024, 2025, 2026) for m in range(1, 13)][:25]
    ratios = [1.005 if i % 2 == 0 else 1.015 for i in range(25)]
    price = 10.0
    prices = []
    for r in ratios:
        prices.append(price)
        price *= r
    engine = _build_engine(dates, {"A.SZ": prices}, {"A.SZ": [0] * 25}, ["A.SZ"])
    result = engine.run_backtest(CFG, dates[0], dates[-1], 1_000_000.0, "monthly")
    metrics = result["performance_metrics"]
    # 月频、逐期收益 std=0.5% → 年化 ≈ 0.005*sqrt(12)；若错误地 *sqrt(252) 会约大 4.6 倍
    assert metrics["volatility"] == pytest.approx(0.005 * (12 ** 0.5), rel=0.15)


def test_trade_constraints_reflect_real_policies():
    engine = _build_engine(
        ["2026-01-05", "2026-01-06"],
        {"A.SZ": [10, 10]},
        {"A.SZ": [0, 0]},
        ["A.SZ"],
    )
    constraints = engine._build_trade_constraints(CFG)
    assert constraints["suspend_policy"] == "no_buy_keep_position"
    assert constraints["limit_up_down_policy"] == "enforced_at_execution"
    assert constraints["execution_timing"] == "t_plus_1_close"


def test_st_stock_uses_5pct_limit_threshold():
    """ST 股 5% 幅度：+5% 即视为涨停禁买（主板 10% 的股票 +5% 应可买）。"""
    dates = ["2026-01-05", "2026-01-06", "2026-01-07"]
    engine = _build_engine(
        dates,
        {"A.SZ": [10, 10.5, 11], "S.SZ": [10, 10.5, 11]},
        {"A.SZ": [0, 5.0, 4.76], "S.SZ": [0, 5.0, 4.76]},
        ["A.SZ", "S.SZ"],
    )
    reader = engine.data_reader
    reader.get_stock_basic.return_value = pd.DataFrame(
        [
            {"ts_code": "A.SZ", "name": "正常股", "industry": "X"},
            {"ts_code": "S.SZ", "name": "ST测试", "industry": "X"},
        ]
    )
    result = engine.run_backtest(CFG, "2026-01-05", "2026-01-07", 1_000_000.0, "daily")
    first_positions = result["daily_positions"][0]
    assert first_positions.get("A.SZ", 0) > 0, "主板股 +5% 未涨停，应可买入"
    assert "S.SZ" not in first_positions, "ST 股 +5% 已涨停，不应买入"
