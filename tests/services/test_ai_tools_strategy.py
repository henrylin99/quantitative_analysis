"""AI 策略工具层测试：save_strategy / run_strategy / compare_backtests / run_backtest 权重。"""

from types import SimpleNamespace

import pandas as pd
import pytest
from flask import Flask

import app.services.ai.tools as ai_tools
from app.services.ai.tools import execute_tool, get_tool_specs


@pytest.fixture()
def app(tmp_path, monkeypatch):
    # ParquetStateStore 缺省从 DATA_DIR 环境变量解析根目录——必须指到
    # tmp，否则工具测试会写进真实 ml_factor_state
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = Flask(__name__)
    app.config.update(TESTING=True, DATA_DIR=str(tmp_path))
    with app.app_context():
        yield app
    ai_tools.reset_singletons()


@pytest.fixture()
def factor_engine_stub(monkeypatch):
    """因子清单桩：只登记 momentum_20 / pe_percentile 两个因子。"""

    class _Engine:
        def get_factor_list(self):
            return [
                {"factor_id": "momentum_20"},
                {"factor_id": "pe_percentile"},
            ]

    monkeypatch.setattr(ai_tools, "_get_factor_engine", lambda: _Engine())


@pytest.fixture()
def no_background_thread(monkeypatch):
    launched = []

    def _capture(*args, **kwargs):
        thread = SimpleNamespace(args=kwargs.get("args") or (), start=lambda: None)
        launched.append(thread)
        return thread

    monkeypatch.setattr(
        "app.services.strategy_service.threading.Thread", _capture
    )
    return launched


_SAVE_ARGS = {
    "name": "动量+低估值",
    "factor_ids": ["momentum_20", "pe_percentile"],
    "weights": {"momentum_20": 0.6, "pe_percentile": -0.4},
    "factor_directions": {"pe_percentile": "low"},
    "top_n": 30,
    "start_date": "2026-01-01",
    "end_date": "2026-06-30",
    "description": "动量为主、估值反向",
}


def _ok(result):
    assert result.get("ok") is True, result
    return result["result"]


class TestSaveStrategy:
    def test_saves_and_returns_version(self, app, factor_engine_stub):
        out = _ok(execute_tool("save_strategy", dict(_SAVE_ARGS)))
        assert out["version"] == 1
        assert out["strategy_config"]["engine_config"]["weights"]["pe_percentile"] == -0.4

    def test_same_name_upgrades(self, app, factor_engine_stub):
        _ok(execute_tool("save_strategy", dict(_SAVE_ARGS)))
        out = _ok(execute_tool("save_strategy", dict(_SAVE_ARGS, top_n=50)))
        assert out["version"] == 2

    def test_rejects_unknown_factor(self, app, factor_engine_stub):
        result = execute_tool(
            "save_strategy", dict(_SAVE_ARGS, factor_ids=["nope_factor"])
        )
        assert result["ok"] is False
        assert "nope_factor" in result["error"]

    def test_rejects_bad_direction(self, app, factor_engine_stub):
        result = execute_tool(
            "save_strategy", dict(_SAVE_ARGS, factor_directions={"momentum_20": "middle"})
        )
        assert result["ok"] is False

    def test_blocked_without_allow_actions(self, app, factor_engine_stub):
        result = execute_tool("save_strategy", dict(_SAVE_ARGS), allow_actions=False)
        assert result["ok"] is False


class TestRunStrategyTool:
    def test_runs_saved_strategy_with_overrides(self, app, factor_engine_stub, no_background_thread):
        _ok(execute_tool("save_strategy", dict(_SAVE_ARGS)))
        out = _ok(
            execute_tool(
                "run_strategy",
                {"strategy_name": "动量+低估值", "top_n": 10, "end_date": "20260630"},
            )
        )
        assert out["status"] == "queued"
        assert out["strategy_config"]["top_n"] == 10
        assert out["end_date"] == "2026-06-30"  # YYYYMMDD 归一化
        assert no_background_thread, "应启动后台回测线程"

    def test_unknown_strategy_fails(self, app, factor_engine_stub, no_background_thread):
        result = execute_tool("run_strategy", {"strategy_name": "不存在"})
        assert result["ok"] is False

    def test_blocked_without_allow_actions(self, app, factor_engine_stub, no_background_thread):
        result = execute_tool("run_strategy", {"strategy_name": "x"}, allow_actions=False)
        assert result["ok"] is False


class TestCompareBacktests:
    def _seed_runs(self, app):
        from app.services.parquet_state_store import (
            BacktestRepository,
            ParquetStateStore,
        )

        repo = BacktestRepository(ParquetStateStore())
        ids = []
        for ret in (0.10, 0.15):
            run = repo.create_run(
                {"selection_method": "factor_based", "factor_list": ["momentum_20"]},
                "2026-01-01", "2026-06-30", 1000000.0, "monthly",
            )
            repo.update_summary(run["id"], {"status": "succeeded"})
            repo.save_result(
                run["id"],
                {"performance_metrics": {"total_return": ret, "sharpe_ratio": ret * 10}},
            )
            ids.append(run["id"])
        return ids

    def test_compares_two_runs(self, app):
        r1, r2 = self._seed_runs(app)
        out = _ok(execute_tool("compare_backtests", {"run_ids": [r1, r2]}))
        assert [row["run_id"] for row in out["runs"]] == [r1, r2]
        assert out["runs"][1]["total_return"] == 0.15

    def test_validates_run_count(self, app):
        result = execute_tool("compare_backtests", {"run_ids": [1]})
        assert result["ok"] is False


class TestRunBacktestWeights:
    def test_weights_dict_passthrough(self, app, monkeypatch, no_background_thread):
        captured = {}

        class _Repo:
            def create_run(self, strategy_config, **kwargs):
                captured["config"] = strategy_config
                return {"id": 77, **kwargs}

            def update_summary(self, *a, **k):
                return None

        import app.services.ai.tools as tools_mod

        monkeypatch.setattr(
            "app.services.parquet_state_store.BacktestRepository", lambda store: _Repo()
        )
        result = execute_tool(
            "run_backtest",
            {
                "factor_ids": ["momentum_20", "pe_percentile"],
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
                "weights": {"momentum_20": 1.0, "pe_percentile": -1.0},
            },
        )
        assert result["ok"] is True, result
        assert captured["config"]["weights"] == {
            "momentum_20": 1.0,
            "pe_percentile": -1.0,
        }

    def test_weights_array_must_align(self, app):
        result = execute_tool(
            "run_backtest",
            {
                "factor_ids": ["momentum_20"],
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
                "weights": [1.0, 2.0],
            },
        )
        assert result["ok"] is False
        assert "一致" in result["error"]


def test_strategy_tools_registered_with_kinds():
    specs = {t["function"]["name"]: t for t in get_tool_specs()}
    for name in ("save_strategy", "run_strategy", "compare_backtests"):
        assert name in specs
    read_only_names = {t["function"]["name"] for t in get_tool_specs(allow_actions=False)}
    assert "compare_backtests" in read_only_names
    assert "save_strategy" not in read_only_names


class TestDslTools:
    """run_backtest / save_strategy 的 DSL 规则模式。"""

    _DSL_ARGS = {
        "name": "动量强势规则",
        "dsl_filter": "rank(momentum_20) > 0.5 and pe_percentile < 0.6",
        "dsl_order_by": "rank(momentum_20) - rank(pe_percentile)",
        "top_n": 20,
        "start_date": "2026-01-01",
        "end_date": "2026-06-30",
    }

    def test_save_dsl_strategy(self, app, factor_engine_stub):
        out = _ok(execute_tool("save_strategy", dict(self._DSL_ARGS)))
        engine = out["strategy_config"]["engine_config"]
        assert engine["selection_method"] == "dsl_rule"
        assert engine["factor_list"] == ["momentum_20", "pe_percentile"]
        assert engine["dsl"]["filter"].startswith("rank(momentum_20)")

    def test_save_dsl_unknown_factor_rejected(self, app, factor_engine_stub):
        result = execute_tool(
            "save_strategy",
            dict(self._DSL_ARGS, dsl_order_by="rank(nope_factor)"),
        )
        assert result["ok"] is False
        assert "nope_factor" in result["error"]

    def test_save_dsl_mutually_exclusive_with_factor_ids(self, app, factor_engine_stub):
        result = execute_tool(
            "save_strategy",
            dict(self._DSL_ARGS, factor_ids=["momentum_20"]),
        )
        assert result["ok"] is False
        assert "互斥" in result["error"]

    def test_save_dsl_rejects_weights(self, app, factor_engine_stub):
        result = execute_tool(
            "save_strategy",
            dict(self._DSL_ARGS, weights={"momentum_20": 1.0}),
        )
        assert result["ok"] is False

    def test_save_dsl_requires_order_by(self, app, factor_engine_stub):
        result = execute_tool(
            "save_strategy",
            dict(self._DSL_ARGS, dsl_order_by="", dsl_filter="momentum_20 > 0"),
        )
        assert result["ok"] is False
        assert "dsl_order_by" in result["error"]

    def test_run_backtest_dsl_passthrough(self, app, monkeypatch, factor_engine_stub, no_background_thread):
        captured = {}

        class _Repo:
            def create_run(self, strategy_config, **kwargs):
                captured["config"] = strategy_config
                return {"id": 78, **kwargs}

            def update_summary(self, *a, **k):
                return None

        monkeypatch.setattr(
            "app.services.parquet_state_store.BacktestRepository", lambda store: _Repo()
        )
        result = execute_tool(
            "run_backtest",
            {
                "dsl_order_by": "rank(momentum_20) - rank(pe_percentile)",
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert result["ok"] is True, result
        assert captured["config"]["selection_method"] == "dsl_rule"
        assert captured["config"]["factor_list"] == ["momentum_20", "pe_percentile"]

    def test_run_backtest_dsl_rejects_weights(self, app, factor_engine_stub, no_background_thread):
        result = execute_tool(
            "run_backtest",
            {
                "dsl_order_by": "momentum_20",
                "weights": {"momentum_20": 1.0},
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
            },
        )
        assert result["ok"] is False
        assert "weights" in result["error"]

    def test_run_saved_dsl_strategy(self, app, factor_engine_stub, no_background_thread):
        _ok(execute_tool("save_strategy", dict(self._DSL_ARGS)))
        out = _ok(execute_tool("run_strategy", {"strategy_name": "动量强势规则", "top_n": 5}))
        assert out["status"] == "queued"
        assert out["strategy_config"]["selection_method"] == "dsl_rule"
        assert out["strategy_config"]["top_n"] == 5


class TestSuggestStrategyChanges:
    def _seed_strategy_with_runs(self, app):
        from app.services.parquet_state_store import (
            BacktestRepository,
            ParquetStateStore,
        )
        out = _ok(execute_tool("save_strategy", {
            "name": "待优化", "factor_ids": ["momentum_20"], "top_n": 30,
            "start_date": "2026-01-01", "end_date": "2026-06-30",
        }))
        repo = BacktestRepository(ParquetStateStore())
        run_ids = []
        for _ in range(4):  # 同区间 4 次成功 run → 触发过拟合预警
            run = repo.create_run(
                {"selection_method": "factor_based", "factor_list": ["momentum_20"],
                 "strategy_name": "待优化", "strategy_version": 1},
                "2026-01-01", "2026-06-30", 1000000.0, "monthly",
            )
            repo.update_summary(run["id"], {"status": "succeeded"})
            repo.save_result(run["id"], {"performance_metrics": {"total_return": 0.1}})
            run_ids.append(run["id"])
        assert out["version"] == 1
        return run_ids

    def test_suggest_packages_context(self, app, factor_engine_stub):
        self._seed_strategy_with_runs(app)
        out = _ok(execute_tool(
            "suggest_strategy_changes", {"strategy_name": "待优化"},
        ))
        assert out["latest_version"]["name"] == "待优化"
        assert out["version_count"] == 1
        assert out["succeeded_run_count"] == 4
        assert out["same_range_iterations"] == 4
        assert "过拟合" in out["overfit_warning"]
        assert "未经用户确认" in out["note"]

    def test_suggest_no_warning_below_threshold(self, app, factor_engine_stub):
        from app.services.parquet_state_store import (
            BacktestRepository,
            ParquetStateStore,
        )

        _ok(execute_tool("save_strategy", {
            "name": "低迭代", "factor_ids": ["momentum_20"], "top_n": 30,
        }))
        repo = BacktestRepository(ParquetStateStore())
        run = repo.create_run(
            {"strategy_name": "低迭代", "strategy_version": 1},
            "2026-01-01", "2026-06-30", 1000000.0, "monthly",
        )
        repo.update_summary(run["id"], {"status": "succeeded"})
        out = _ok(execute_tool(
            "suggest_strategy_changes", {"strategy_name": "低迭代"},
        ))
        assert out["same_range_iterations"] == 1
        assert out["overfit_warning"] is None

    def test_suggest_unknown_strategy(self, app):
        result = execute_tool(
            "suggest_strategy_changes", {"strategy_name": "不存在"},
        )
        assert result["ok"] is False
