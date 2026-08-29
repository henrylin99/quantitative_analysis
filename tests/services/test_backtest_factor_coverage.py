"""回测因子覆盖率前置校验的回归测试。

因子库缺失数据时选股为空、日期被静默跳过、回测照常出指标——
这种假结果必须在入口拒绝。
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.backtest_engine import BacktestEngine

pytestmark = pytest.mark.module_backtest

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]

CFG = {
    "selection_method": "factor_based",
    "factor_list": ["momentum_20d"],
    "top_n": 5,
    "commission_rate": 0.0,
    "slippage_rate": 0.0,
    "optimization": {"method": "equal_weight"},
}


def _build_engine(factor_values_frame):
    engine = BacktestEngine()
    engine.backtest_repo = MagicMock()
    engine.backtest_repo.create_run.return_value = {"id": 1}
    engine.factor_repo = MagicMock()
    engine.factor_repo.get_values.return_value = factor_values_frame

    reader = MagicMock()
    reader.get_trade_dates.return_value = DATES
    reader.get_daily.return_value = pd.DataFrame()
    reader.get_stock_basic.return_value = pd.DataFrame(
        [{"ts_code": "A.SZ", "name": "A", "industry": "X"}]
    )
    engine.data_reader = reader

    engine._get_stock_selection = lambda cfg, d: [
        {"ts_code": "A.SZ", "composite_score": 1.0}
    ]
    return engine


def _covered_frame(dates):
    return pd.DataFrame(
        [
            {"ts_code": "A.SZ", "trade_date": d, "factor_id": "momentum_20d",
             "factor_value": 0.1}
            for d in dates
        ]
    )


def test_backtest_rejected_when_factor_values_missing():
    engine = _build_engine(pd.DataFrame())

    result = engine.run_backtest(CFG, DATES[0], DATES[-1], 1_000_000.0, "daily")

    assert "error" in result
    assert "因子值缺失" in result["error"]
    assert "factor_compute" in result["error"], "错误信息应提示补数据的方式"
    # 校验必须发生在创建回测记录之前，不留悬挂的 running 记录
    engine.backtest_repo.create_run.assert_not_called()


def test_backtest_reports_missing_dates():
    covered = _covered_frame(DATES[:2])
    engine = _build_engine(covered)

    result = engine.run_backtest(CFG, DATES[0], DATES[-1], 1_000_000.0, "daily")

    assert "error" in result
    assert "2/4" in result["error"]
    assert DATES[2] in result["error"]


def test_backtest_proceeds_when_coverage_complete():
    engine = _build_engine(_covered_frame(DATES))

    result = engine.run_backtest(CFG, DATES[0], DATES[-1], 1_000_000.0, "daily")

    assert result.get("success") is True
    engine.factor_repo.get_values.assert_called_once()


def test_skip_flag_bypasses_coverage_check():
    engine = _build_engine(pd.DataFrame())
    config = {**CFG, "skip_factor_coverage_check": True}

    result = engine.run_backtest(config, DATES[0], DATES[-1], 1_000_000.0, "daily")

    assert result.get("success") is True
    engine.factor_repo.get_values.assert_not_called()


def test_non_factor_selection_skips_check():
    engine = _build_engine(pd.DataFrame())
    config = {**CFG, "selection_method": "ml_based", "factor_list": []}

    result = engine.run_backtest(config, DATES[0], DATES[-1], 1_000_000.0, "daily")

    assert result.get("success") is True
