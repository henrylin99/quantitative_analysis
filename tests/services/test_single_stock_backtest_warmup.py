"""单股票回测引擎的信号预热与成本口径回归测试。

- 信号必须在"全量数据"（含回测区间前的预热段）上计算后再截取窗口：
  否则长窗口均线在区间头部是 NaN，调用方多取的预热数据白取
- 窗口首日可承接最后一根预热 bar 的信号（t+1 语义）
- 滑点与佣金双边收取，计入买入成本与期末强平
"""
import pandas as pd
import pytest

from app.services.single_stock_backtest import SingleStockBacktestEngine

pytestmark = pytest.mark.module_backtest


def _make_data(closes, start_idx=0):
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    history = [
        {"ts_code": "000001.SZ", "trade_date": d.strftime("%Y-%m-%d"), "close": c}
        for d, c in zip(dates, closes)
    ]
    factors = [
        {"ts_code": "000001.SZ", "trade_date": d.strftime("%Y-%m-%d")}
        for d in dates
    ]
    return history, factors, dates


def _window_dates(dates, start_idx, end_idx):
    return dates[start_idx].strftime("%Y-%m-%d"), dates[end_idx].strftime("%Y-%m-%d")


def test_warmup_signals_available_at_window_start():
    """金叉发生在窗口第 2 根 bar：必须靠预热段算出信号并成交。

    旧实现先截取窗口再算信号，ma_long（窗口=5）在窗口前 4 根 bar 全为
    NaN，这笔交易会丢失。
    """
    # 前 20 根横盘 9.5（预热段），窗口内第 2 根 bar 急涨触发金叉
    closes = [9.5] * 20 + [9.5, 10.5] + [11.0] * 10
    history, factors, dates = _make_data(closes)

    start_text, end_text = _window_dates(dates, 20, 31)
    config = {
        "ts_code": "000001.SZ",
        "strategy_type": "ma_cross",
        "start_date": start_text,
        "end_date": end_text,
        "initial_capital": 100000.0,
        "commission_rate": 0.0,
        "params": {"ma_short": 3, "ma_long": 5},
    }
    engine = SingleStockBacktestEngine(config)
    result = engine.run_backtest(history, factors)

    buys = [t for t in result["trades"] if t["action"] == "buy"]
    assert buys, "窗口内的金叉应产生买入交易（依赖预热段数据）"
    # 金叉在窗口索引 1（日期索引 21），t+1 成交在窗口索引 2
    assert buys[0]["date"] == dates[22].strftime("%Y-%m-%d")


def test_pre_window_signal_executes_on_first_window_day():
    """最后一根预热 bar 产生的信号，应在窗口首日成交（t+1）。

    窗口外不交易、不记账：daily_values 不含预热段。
    """
    closes = [9.5] * 20 + [10.5] + [11.0] * 11
    history, factors, dates = _make_data(closes)

    start_text, end_text = _window_dates(dates, 21, 31)
    config = {
        "ts_code": "000001.SZ",
        "strategy_type": "ma_cross",
        "start_date": start_text,
        "end_date": end_text,
        "initial_capital": 100000.0,
        "commission_rate": 0.0,
        "params": {"ma_short": 3, "ma_long": 5},
    }
    engine = SingleStockBacktestEngine(config)
    result = engine.run_backtest(history, factors)

    buys = [t for t in result["trades"] if t["action"] == "buy"]
    assert buys, "预热段末尾的金叉应在窗口首日成交"
    assert buys[0]["date"] == dates[21].strftime("%Y-%m-%d"), (
        "预热 bar 的信号必须在窗口首日（t+1）执行"
    )


def test_slippage_applied_to_buy_and_liquidation():
    """滑点与佣金双边收取：买入成本含滑点，期末强平也含滑点。"""
    closes = [9.5] * 20 + [9.5, 10.5] + [11.0] * 10
    history, factors, dates = _make_data(closes)
    start_text, end_text = _window_dates(dates, 20, 31)

    config = {
        "ts_code": "000001.SZ",
        "strategy_type": "ma_cross",
        "start_date": start_text,
        "end_date": end_text,
        "initial_capital": 100000.0,
        "commission_rate": 0.0,
        "slippage_rate": 0.01,
        "params": {"ma_short": 3, "ma_long": 5},
    }
    engine = SingleStockBacktestEngine(config)
    result = engine.run_backtest(history, factors)

    buys = [t for t in result["trades"] if t["action"] == "buy"]
    assert buys
    buy = buys[0]
    assert buy["slippage"] == pytest.approx(buy["quantity"] * buy["price"] * 0.01)
    assert buy["amount"] == pytest.approx(buy["quantity"] * buy["price"] * 1.01)
    perf = result["performance"]
    assert perf["liquidation_cost"] > 0, "期末强平成本应包含滑点"
    assert perf["total_cost"] == pytest.approx(perf["total_commission"])
