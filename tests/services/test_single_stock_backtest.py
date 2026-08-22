"""单股票策略回测引擎的回归测试（从 analysis_api 抽取 + t+1 执行修复）。"""
import pandas as pd
import pytest

from app.services.single_stock_backtest import SingleStockBacktestEngine


def _make_data(closes):
    """构造日线 + 空 因子表：收盘价序列，日期连续。"""
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    history = [
        {"ts_code": "000001.SZ", "trade_date": d.strftime("%Y-%m-%d"), "close": c}
        for d, c in zip(dates, closes)
    ]
    factors = [
        {"ts_code": "000001.SZ", "trade_date": d.strftime("%Y-%m-%d")}
        for d in dates
    ]
    return history, factors


def test_buy_signal_executes_next_day_close():
    """金叉在 t 日收盘确认，成交必须在 t+1 收盘价，而非 t 日本身。"""
    # 前 10 天下行（短均线在下），第 11 天起急涨触发金叉
    closes = [10 - i * 0.1 for i in range(10)] + [11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 16.0]
    history, factors = _make_data(closes)

    config = {
        "ts_code": "000001.SZ",
        "strategy_type": "ma_cross",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "initial_capital": 100000.0,
        "commission_rate": 0.0,
        "params": {"ma_short": 3, "ma_long": 5},
    }
    engine = SingleStockBacktestEngine(config)
    result = engine.run_backtest(history, factors)

    assert result["trades"], "应产生买入交易"
    buy = result["trades"][0]
    assert buy["action"] == "buy"
    # 金叉日的索引（信号日）与成交日索引应相差 1
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D").strftime("%Y-%m-%d").tolist()
    signal_idx = closes.index(11.0)  # 第 11 天大涨确认金叉
    assert dates.index(buy["date"]) == signal_idx + 1, (
        f"成交日 {buy['date']} 应为信号日 {dates[signal_idx]} 的下一个交易日"
    )


def test_no_trades_returns_default_performance():
    history, factors = _make_data([10.0] * 20)  # 匀速横盘无信号
    config = {
        "ts_code": "000001.SZ",
        "strategy_type": "ma_cross",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "initial_capital": 100000.0,
        "params": {"ma_short": 3, "ma_long": 5},
    }
    engine = SingleStockBacktestEngine(config)
    result = engine.run_backtest(history, factors)
    assert result["performance"]["total_trades"] == 0
    assert result["performance"]["final_capital"] == pytest.approx(100000.0)
