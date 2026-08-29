"""量化正确性修复的回归测试（2026-08 第二轮）。

覆盖:
- 收益率价格用后复权口径（除权缺口不再污染动量/标签）
- 股票池按历史时点过滤（退市股/未来上市股）
- 表达式引擎禁止负 shift / 全序列 rank
- ML 预测拒绝训练区间内的 in-sample 请求，兜底日期格式统一 YYYY-MM-DD
- 卖出印花税计入交易成本
- 组合优化协方差按调仓日截断估计
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.data_reader import ParquetDataReader
from app.services.factor_expression_engine import FactorExpressionEngine
from app.services.factor_engine import FactorEngine


pytestmark = [
    pytest.mark.module_factor_engine,
    pytest.mark.module_feature_engineering,
    pytest.mark.module_ml_model,
]


# ---------------------------------------------------------------------------
# 复权口径
# ---------------------------------------------------------------------------


def test_get_return_prices_prefers_hfq_close(monkeypatch):
    """有后复权数据时，close 应替换为 close_hfq（除权缺口不再进入收益率）。"""
    reader = ParquetDataReader()
    daily = pd.DataFrame(
        {
            "ts_code": ["A.SZ"] * 3,
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "close": [10.0, 5.0, 5.1],  # 01-03 除权造成 -50% 假缺口
        }
    )
    sf = pd.DataFrame(
        {
            "ts_code": ["A.SZ"] * 3,
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "close_hfq": [1000.0, 1005.0, 1010.0],
        }
    )
    monkeypatch.setattr(reader, "get_daily", lambda **kw: daily)
    monkeypatch.setattr(reader, "get_stk_factor", lambda **kw: sf)

    out = reader.get_return_prices()
    assert sorted(out["close"].tolist()) == [1000.0, 1005.0, 1010.0]


def test_get_return_prices_falls_back_per_stock(monkeypatch):
    """复权覆盖率不足的股票整体退回复权价，且不与复权价混拼。"""
    reader = ParquetDataReader()
    daily = pd.DataFrame(
        {
            "ts_code": ["A.SZ", "B.SZ"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "close": [10.0, 20.0],
        }
    )
    sf = pd.DataFrame(
        {
            "ts_code": ["B.SZ"],
            "trade_date": pd.to_datetime(["2024-01-02"]),
            "close_hfq": [2000.0],
        }
    )
    monkeypatch.setattr(reader, "get_daily", lambda **kw: daily)
    monkeypatch.setattr(reader, "get_stk_factor", lambda **kw: sf)

    out = reader.get_return_prices().set_index("ts_code")
    assert out.loc["A.SZ", "close"] == 10.0, "无复权数据的股票保持不复权价"
    assert out.loc["B.SZ", "close"] == 2000.0, "有复权数据的股票使用后复权价"


# ---------------------------------------------------------------------------
# 股票池 point-in-time 过滤
# ---------------------------------------------------------------------------


def test_universe_filter_removes_future_listing_and_delisted():
    engine = FactorEngine.__new__(FactorEngine)  # 只测纯函数，不触发初始化 IO
    basic = pd.DataFrame(
        [
            {"ts_code": "OLD", "list_date": "2010-01-01", "delist_date": None},
            {
                "ts_code": "DELISTED",
                "list_date": "2010-01-01",
                "delist_date": "2021-06-30",
            },
            {"ts_code": "NEW", "list_date": "2025-01-01", "delist_date": None},
        ]
    )
    codes = engine.filter_universe_asof(basic, "2024-06-30")
    assert set(codes) == {"OLD"}, "退市股与未上市股都不应出现在历史时点的股票池"


# ---------------------------------------------------------------------------
# 表达式引擎时间因果性
# ---------------------------------------------------------------------------


def _expr_df():
    return pd.DataFrame({"close": [10.0, 11.0, 12.0, 13.0, 14.0]})


@pytest.mark.parametrize(
    "expr", ["close.shift(-1)", "close.pct_change(-5)", "close.diff(-2)"]
)
def test_expression_rejects_negative_periods(expr):
    with pytest.raises(ValueError):
        FactorExpressionEngine().evaluate(expr, _expr_df())


def test_expression_rejects_full_series_rank():
    # Series.rank 是整条时间序列上的排名，会把未来价格纳入分母
    with pytest.raises(ValueError):
        FactorExpressionEngine().evaluate("close.rank()", _expr_df())


# ---------------------------------------------------------------------------
# ML 预测防泄漏
# ---------------------------------------------------------------------------


def test_predict_rejects_in_sample_dates(tmp_path, monkeypatch):
    from app.services.ml_models import MLModelManager
    from app.services.parquet_state_store import ParquetStateStore

    manager = MLModelManager(
        state_store=ParquetStateStore(base_dir=str(tmp_path / "state"))
    )
    manager.model_repo.upsert_definition(
        {
            "model_id": "m_leak",
            "model_name": "泄漏模型",
            "model_type": "random_forest",
            "factor_list": ["f1"],
            "target_type": "return_5d",
            "model_params": {},
            "training_config": {"train_end_date": "2024-06-30"},
            "is_active": True,
        }
    )
    manager.models["m_leak"] = MagicMock()
    manager.models["m_leak"].predict.return_value = [0.1]
    manager.scalers["m_leak"] = MagicMock()
    manager.scalers["m_leak"].transform.side_effect = lambda X: X

    factor_data = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": pd.to_datetime(["2024-06-28"]),
            "factor_id": ["f1"],
            "factor_value": [1.0],
        }
    )
    monkeypatch.setattr(
        manager.factor_repo, "get_values", lambda **kw: factor_data.copy()
    )

    out = manager.predict("m_leak", "2024-06-28")
    assert out.empty, "预测日期早于等于训练截止日时必须拒绝（in-sample 泄漏）"

    # 兜底路径：请求日无数据回退最新可用日期时同样拦截
    def empty_then_latest(**kw):
        if kw.get("trade_date") == "2024-07-05":
            return pd.DataFrame()
        return factor_data.copy()

    monkeypatch.setattr(manager.factor_repo, "get_values", empty_then_latest)
    out2 = manager.predict("m_leak", "2024-07-05")
    assert out2.empty, "回退到的日期若仍在训练区间内也必须拒绝"


def test_predict_effective_date_normalized(tmp_path, monkeypatch):
    """兜底到最新日期时 trade_date 必须是 YYYY-MM-DD，否则成为查不到的孤儿数据。"""
    from app.services.ml_models import MLModelManager
    from app.services.parquet_state_store import ParquetStateStore

    manager = MLModelManager(
        state_store=ParquetStateStore(base_dir=str(tmp_path / "state"))
    )
    manager.model_repo.upsert_definition(
        {
            "model_id": "m_fmt",
            "model_name": "格式模型",
            "model_type": "random_forest",
            "factor_list": ["f1"],
            "target_type": "return_5d",
            "model_params": {},
            "training_config": {},
            "is_active": True,
        }
    )

    class FakeModel:
        def predict(self, X):
            import numpy as np

            return np.array([0.3])

    manager.models["m_fmt"] = FakeModel()

    factor_data = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": pd.to_datetime(["2024-08-01"]),
            "factor_id": ["f1"],
            "factor_value": [1.0],
        }
    )

    def latest_only(**kw):
        if kw.get("trade_date") is not None:
            return pd.DataFrame()
        return factor_data.copy()

    monkeypatch.setattr(manager.factor_repo, "get_values", latest_only)

    out = manager.predict("m_fmt", "2024-09-01")
    assert not out.empty
    assert out.iloc[0]["trade_date"] == "2024-08-01"
    assert "00:00:00" not in str(out.iloc[0]["trade_date"])


# ---------------------------------------------------------------------------
# 交易成本：卖出印花税
# ---------------------------------------------------------------------------


def test_stamp_duty_applies_to_sell_side_only():
    from app.services.backtest_engine import BacktestEngine

    engine = BacktestEngine()
    costs = engine._apply_trade_costs(
        trade_value=1_000_000.0,
        commission_rate=0.001,
        slippage_rate=0.0,
        sell_value=400_000.0,
        stamp_duty_rate=0.0005,
    )
    assert costs["commission"] == pytest.approx(1_000.0)
    assert costs["stamp_duty"] == pytest.approx(200.0), "印花税只按卖出金额计"
    assert costs["total_cost"] == pytest.approx(1_200.0)


# ---------------------------------------------------------------------------
# 组合优化：协方差按调仓日截断
# ---------------------------------------------------------------------------


def test_optimizer_risk_model_respects_as_of_date(monkeypatch):
    from app.services import portfolio_optimizer as po

    captured = {}

    class CapturingReader:
        def get_daily(self, ts_codes=None, start_date=None, end_date=None):
            captured["end_date"] = end_date
            return pd.DataFrame()

    monkeypatch.setattr(po, "ParquetDataReader", CapturingReader)

    optimizer = po.PortfolioOptimizer()
    optimizer._estimate_risk_model(["A.SZ", "B.SZ"], as_of_date="2023-05-15")

    assert captured.get("end_date") is not None
    assert str(captured["end_date"]).startswith("2023"), "风险模型窗口必须以调仓日为右边界"


def test_scores_mapped_to_annual_expected_returns():
    from app.services.backtest_engine import BacktestEngine

    engine = BacktestEngine()
    stocks = [
        {"ts_code": f"S{i}.SZ", "composite_score": float(i)} for i in range(-3, 4)
    ]
    er = engine._scores_to_expected_returns(stocks)
    assert er.min() >= -0.15 - 1e-9 and er.max() <= 0.30 + 1e-9
    assert er.nunique() > 3, "排序信息应保留"
