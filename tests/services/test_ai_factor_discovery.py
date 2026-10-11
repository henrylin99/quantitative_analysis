"""AI 因子组合自动发现工具测试（5.4）：体检→去冗余→分位回测→报告存看板。"""

from __future__ import annotations

import pytest

import app.services.ai.tools as ai_tools
from app.services.ai.tools import ToolError, _tool_discover_factor_combo


class _FakeScreening:
    calls = {}

    def screen_factors(self, factor_ids=None, start_date=None, end_date=None,
                       forward_period=5, save=True, **kw):
        _FakeScreening.calls["factor_ids"] = factor_ids
        return {
            "start_date": "2025-10-01", "end_date": "2026-10-01",
            "n_factors": 3,
            "factors": {
                "f_a": {"ic_mean": 0.08, "ic_ir": 0.9, "ic_positive_ratio": 0.8},
                "f_b": {"ic_mean": -0.06, "ic_ir": 0.7, "ic_positive_ratio": 0.3},
                "f_c": {"ic_mean": 0.01, "ic_ir": 0.1, "ic_positive_ratio": 0.5},
            },
        }


class _FakeAnalyzer:
    def __init__(self, *a, **kw):
        pass

    def correlation_matrix(self, factor_ids, start_date=None, end_date=None, **kw):
        # f_b 与 f_a 高度相关 → 应被贪心剔除；f_c 独立
        m = {f: {g: (0.95 if {f, g} == {"f_a", "f_b"} else 0.1)
                 for g in factor_ids} for f in factor_ids}
        return {"matrix": m}

    def quantile_portfolio_backtest(self, factor_id, start_date=None, end_date=None,
                                    holding_days=20, cost_bps=10.0, **kw):
        return {
            "n_periods": 12,
            "long_short_summary": {"annualized_return": 0.12, "sharpe": 1.1,
                                   "max_drawdown": -0.08},
            "groups_summary": {"g5": {"annualized_return": 0.2}},
            "avg_turnover": {"g5": 0.3},
        }


class _FakeSavedStore:
    last_board = None

    def save_board(self, title, content, meta=None):
        _FakeSavedStore.last_board = {"id": 7, "title": title, "content": content}
        return _FakeSavedStore.last_board


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _FakeScreening.calls.clear()
    _FakeSavedStore.last_board = None
    monkeypatch.setattr("app.services.factor_screening.FactorScreeningService",
                        _FakeScreening)
    monkeypatch.setattr("app.services.factor_analyzer.FactorAnalyzer", _FakeAnalyzer)
    monkeypatch.setattr("app.services.ai.saved_items.AiSavedStore", _FakeSavedStore)


def test_discover_selects_low_corr_top_factors():
    result = _tool_discover_factor_combo({"top_k": 2})
    # 排名 f_a > f_b > f_c（|IC|×ICIR）；f_b 与 f_a 相关 0.95 被剔除 → f_a + f_c
    assert result["selected_factors"] == ["f_a", "f_c"]
    assert result["skipped_redundant"]["f_b"]["partner"] == "f_a"
    assert set(result["backtests"]) == {"f_a", "f_c"}
    assert result["backtests"]["f_a"]["long_short"]["sharpe"] == 1.1
    # 报告存看板
    assert result["saved_board"]["id"] == 7
    assert "f_a" in _FakeSavedStore.last_board["content"]
    assert "反向" in _FakeSavedStore.last_board["content"] or "正向" in _FakeSavedStore.last_board["content"]


def test_discover_default_params_passthrough():
    result = _tool_discover_factor_combo(
        {"factor_ids": ["f_a", "f_b"], "top_k": 5, "cost_bps": 15})
    assert _FakeScreening.calls["factor_ids"] == ["f_a", "f_b"]
    # fake 体检不按候选过滤（返回全部 3 个），f_b 相关被剔 → f_a + f_c
    assert result["selected_factors"] == ["f_a", "f_c"]


def test_discover_no_live_factors_raises():
    import app.services.factor_screening as fs
    orig = fs.FactorScreeningService
    fs.FactorScreeningService = _BrokenScreening
    try:
        with pytest.raises(ToolError):
            _tool_discover_factor_combo({})
    finally:
        fs.FactorScreeningService = orig


class _BrokenScreening:
    def screen_factors(self, **kw):
        return {"error": "因子库为空", "factors": {}}
