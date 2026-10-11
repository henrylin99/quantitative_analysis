"""内置因子最小验收样例（整改清单 4.2.1）。

两层验收：
1. 可执行核对——用合成输入直接喂因子计算函数，断言结果等于
   factor_engine.get_builtin_factor_validation_samples() 文档化的计算规则；
   文档与实现任一方漂移都会在此失败。
2. 数据不足行为——窗口长度不够时必须返回空结果（或缺失被丢弃），
   不允许静默产出假 0；除零产生 inf 统一按缺失处理。

覆盖核心因子：momentum_5d / volatility_20d / volume_ratio_20d /
price_to_ma20 / money_flow_strength / cost_deviation。
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.services.factor_engine import FactorEngine

pytestmark = pytest.mark.module_factor_engine


@pytest.fixture(scope="module")
def engine():
    return FactorEngine()


def _return_prices(closes, vols=None):
    n = len(closes)
    rows = {
        "ts_code": ["000001.SZ"] * n,
        "trade_date": pd.date_range("2026-08-01", periods=n, freq="B"),
        "close": closes,
        "vol": vols if vols is not None else [100.0] * n,
    }
    return pd.DataFrame(rows)


def _single_factor_value(result):
    assert not result.empty, "因子结果为空，未产出任何验收值"
    assert set(result.columns) == {"ts_code", "trade_date", "factor_id", "factor_value"}
    return float(result["factor_value"].iloc[-1])


# ---- 1. 可执行核对：文档化的样例期望必须被实现复现 ----


def test_momentum_5d_sample(engine):
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    result = engine._momentum_factor({"return_prices": _return_prices(closes)}, "momentum_5d")
    # 文档：close=[10,11,12,13,14,15] → 15/10-1 = 0.5
    assert _single_factor_value(result) == pytest.approx(0.5)


def test_volatility_20d_sample(engine):
    # 构造 21 个收盘价：首日 100，其后 20 日收益为 5 个 +2%、15 个 0%
    returns = [0.02] * 5 + [0.0] * 15
    closes = [100.0]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    result = engine._volatility_factor({"return_prices": _return_prices(closes)}, "volatility_20d")
    value = _single_factor_value(result)
    # 文档：rolling(20) 日收益标准差；独立于 pandas 手工计算（样本标准差 n-1）
    mean = 0.02 * 5 / 20
    var = (5 * (0.02 - mean) ** 2 + 15 * (0.0 - mean) ** 2) / 19
    assert value == pytest.approx(math.sqrt(var), rel=1e-9)


def test_volume_ratio_20d_sample(engine):
    vols = [10.0] * 20 + [30.0]
    result = engine._volume_ratio_factor({"return_prices": _return_prices([100.0] * 21, vols)}, "volume_ratio_20d")
    # 文档规则：当日量 / 最近20日均量；末窗均值 = (19*10+30)/20 = 11.0
    assert _single_factor_value(result) == pytest.approx(30.0 / 11.0)


def test_price_to_ma20_sample(engine):
    closes = [11.5] * 20 + [21.0]
    result = engine._price_to_ma_factor({"return_prices": _return_prices(closes)}, "price_to_ma20")
    # 文档规则：close / rolling(20).mean() - 1；末窗均价 = (19*11.5+21)/20
    ma = (19 * 11.5 + 21.0) / 20
    assert _single_factor_value(result) == pytest.approx(21.0 / ma - 1)


def test_money_flow_strength_sample(engine):
    moneyflow = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-09-30",
                "buy_sm_amount": 250.0,
                "buy_md_amount": 125.0,
                "buy_lg_amount": 400.0,
                "buy_elg_amount": 225.0,
                "sell_lg_amount": 0.0,
                "sell_elg_amount": 0.0,
            }
        ]
    )
    result = engine._money_flow_strength_factor({"moneyflow": moneyflow}, "money_flow_strength")
    # 文档：大单净流入 625 / 总成交额 1000 = 0.625
    assert _single_factor_value(result) == pytest.approx(0.625)


def test_cost_deviation_sample(engine):
    daily = pd.DataFrame(
        [{"ts_code": "000001.SZ", "trade_date": "2026-09-30", "close": 11.5}]
    )
    cyq = pd.DataFrame(
        [{"ts_code": "000001.SZ", "trade_date": "2026-09-30", "weight_avg": 10.0}]
    )
    result = engine._cost_deviation_factor({"daily": daily, "cyq": cyq}, "cost_deviation")
    # 文档：(11.5 - 10.0) / 10.0 = 0.15
    assert _single_factor_value(result) == pytest.approx(0.15)


# ---- 2. 文档-实现一致性守卫：样例清单不得缺少可执行验收 ----


def test_documented_samples_all_have_executable_cases(engine):
    documented = {s["factor_id"] for s in engine.get_builtin_factor_validation_samples()}
    executable = {
        "momentum_5d",
        "volatility_20d",
        "volume_ratio_20d",
        "price_to_ma20",
        "money_flow_strength",
        "cost_deviation",
    }
    assert documented == executable, (
        f"样例文档与可执行验收不对齐：文档多出 {documented - executable}，"
        f"可执行多出 {executable - documented}（新增样例须同步补计算核对）"
    )


def test_documented_samples_required_fields_exist_in_sources(engine):
    for sample in engine.get_builtin_factor_validation_samples():
        sources = engine.BUILTIN_FACTOR_SOURCES.get(sample["factor_id"])
        assert sources, f"{sample['factor_id']} 未声明数据源，样例无法计算"
        assert sample["required_fields"], f"{sample['factor_id']} 样例缺 required_fields"
        assert sample["calculation_rule"] and sample["sample_expectation"]


# ---- 3. 数据不足行为：空窗口不出假 0，inf 按缺失处理 ----


@pytest.mark.parametrize(
    "factor_id,data,factor_func",
    [
        # 3 行 < 6 日窗口：pct_change(5) 全 NaN
        ("momentum_5d", {"return_prices": _return_prices([10.0, 11.0, 12.0])}, "_momentum_factor"),
        # 10 行 < 21 日窗口：rolling(20).std() 全 NaN
        ("volatility_20d", {"return_prices": _return_prices([10.0 + i * 0.1 for i in range(10)])}, "_volatility_factor"),
        # 15 行 < 21 日窗口：rolling(20) 均线不可得
        ("price_to_ma20", {"return_prices": _return_prices([10.0 + i * 0.1 for i in range(15)])}, "_price_to_ma_factor"),
    ],
)
def test_insufficient_window_returns_empty(engine, factor_id, data, factor_func):
    result = getattr(engine, factor_func)(data, factor_id)
    assert result.empty, f"{factor_id} 窗口不足时不应产出因子值"


def test_zero_denominator_becomes_missing_not_inf(engine):
    # 资金流四档全 0：除零产生 inf → _finalize_factor_result 必须按缺失丢弃
    moneyflow = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-09-30",
                "buy_sm_amount": 0.0,
                "buy_md_amount": 0.0,
                "buy_lg_amount": 0.0,
                "buy_elg_amount": 0.0,
                "sell_lg_amount": 0.0,
                "sell_elg_amount": 0.0,
            }
        ]
    )
    result = engine._money_flow_strength_factor({"moneyflow": moneyflow}, "money_flow_strength")
    assert result.empty
