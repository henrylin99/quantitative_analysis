"""命名策略服务测试：保存/升版、按名回测（参数覆盖 + 后台线程编排）、多 run 对比。"""

import threading

import pytest

from app.services.parquet_state_store import (
    BacktestRepository,
    ParquetStateStore,
    StrategyRepository,
)
from app.services.strategy_service import (
    StrategyError,
    StrategyService,
    build_strategy_config,
)


@pytest.fixture()
def service(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    return StrategyService(StrategyRepository(store), BacktestRepository(store))


@pytest.fixture()
def no_background_thread(monkeypatch):
    """拦截后台线程：run_strategy 只验证编排（建 run/参数覆盖），不真跑回测。"""

    class _FakeThread:
        def __init__(self, *args, **kwargs):
            self.args = kwargs.get("args") or (args[1] if len(args) > 1 else ())
            self.kwargs = kwargs

        def start(self):
            pass

    launched = []
    _FakeThread.instances = launched

    def _capture(*args, **kwargs):
        t = _FakeThread(*args, **kwargs)
        launched.append(t)
        return t

    monkeypatch.setattr(
        "app.services.strategy_service.threading.Thread", _capture
    )
    return launched


def _config(**overrides):
    base = dict(
        factor_ids=["momentum_20", "pe_percentile"],
        weights={"momentum_20": 0.6, "pe_percentile": -0.4},
        top_n=30,
        start_date="2026-01-01",
        end_date="2026-06-30",
    )
    base.update(overrides)
    return build_strategy_config(**base)


class TestBuildStrategyConfig:
    def test_assembles_engine_config_and_params(self):
        config = _config()
        assert config["engine_config"]["factor_list"] == ["momentum_20", "pe_percentile"]
        assert config["engine_config"]["weights"]["pe_percentile"] == -0.4
        assert config["params"]["start_date"] == "2026-01-01"

    def test_rejects_empty_factors_and_bad_frequency(self):
        with pytest.raises(StrategyError):
            build_strategy_config(factor_ids=[])
        with pytest.raises(StrategyError):
            build_strategy_config(factor_ids=["a"], rebalance_frequency="yearly")

    def test_rejects_weights_for_unknown_factor(self):
        with pytest.raises(StrategyError):
            build_strategy_config(
                factor_ids=["a"],
                weights={"not_in_list": 1.0},
            )


class TestSaveAndVersioning:
    def test_same_name_upgrades_version_and_keeps_history(self, service):
        first = service.save_strategy("动量策略", _config(), description="v1 描述")
        assert first["version"] == 1 and first["is_latest"] is True

        second = service.save_strategy("动量策略", _config(top_n=50), description="v2 描述")
        assert second["version"] == 2

        latest = service.strategy_repo.get_strategy("动量策略")
        assert latest["version"] == 2
        assert latest["strategy_config"]["engine_config"]["top_n"] == 50

        history = service.strategy_repo.list_strategies(include_history=True)
        assert [h["version"] for h in history if h["name"] == "动量策略"] == [1, 2]
        assert len(service.strategy_repo.list_strategies()) == 1  # 默认只列 latest

    def test_get_specific_version(self, service):
        service.save_strategy("s", _config(top_n=10))
        service.save_strategy("s", _config(top_n=20))
        assert service.strategy_repo.get_strategy("s", version=1)[
            "strategy_config"
        ]["engine_config"]["top_n"] == 10

    def test_save_rejects_foreign_config(self, service):
        with pytest.raises(StrategyError):
            service.save_strategy("s", {"engine_config": {}})

    def test_delete_removes_whole_family(self, service):
        service.save_strategy("s", _config())
        service.save_strategy("s", _config(top_n=20))
        assert service.strategy_repo.delete_strategy("s") == 2
        assert service.strategy_repo.get_strategy("s") is None


class TestRunStrategy:
    def test_runs_latest_with_defaults(self, service, no_background_thread):
        service.save_strategy("s", _config())
        run = service.run_strategy("s")

        assert run["status"] == "queued"
        assert run["strategy_version"] == 1
        assert run["strategy_config"]["strategy_name"] == "s"
        assert run["strategy_config"]["weights"]["pe_percentile"] == -0.4
        # 后台线程收到了完整执行参数
        thread_args = no_background_thread[0].args
        assert thread_args[0] == run["run_id"]
        assert thread_args[2] == "2026-01-01" and thread_args[3] == "2026-06-30"
        # run 记录落库且带溯源字段
        stored = service.backtest_repo.get_run(run["run_id"])
        assert stored["strategy_config"]["strategy_name"] == "s"

    def test_overrides_override_without_mutating_definition(self, service, no_background_thread):
        service.save_strategy("s", _config())
        run = service.run_strategy(
            "s",
            overrides={"top_n": 5, "weights": {"momentum_20": 1.0, "pe_percentile": -1.0}},
        )
        assert run["strategy_config"]["top_n"] == 5
        assert run["strategy_config"]["weights"]["pe_percentile"] == -1.0
        # 策略定义未被覆盖污染
        latest = service.strategy_repo.get_strategy("s")
        assert latest["strategy_config"]["engine_config"]["top_n"] == 30

    def test_missing_dates_require_overrides(self, service):
        service.save_strategy("s", _config(start_date="", end_date=""))
        with pytest.raises(StrategyError):
            service.run_strategy("s")
        run = service.run_strategy(
            "s", overrides={"start_date": "2026-02-01", "end_date": "2026-06-30"}
        )
        assert run["start_date"] == "2026-02-01"

    def test_unknown_strategy_raises(self, service):
        with pytest.raises(StrategyError):
            service.run_strategy("不存在")


class TestCompareRuns:
    def _make_run(self, service, start, end, total_return, sharpe, status="succeeded"):
        run = service.backtest_repo.create_run(
            {"selection_method": "factor_based", "factor_list": ["a"]},
            start, end, 1000000.0, "monthly",
        )
        service.backtest_repo.update_summary(run["id"], {"status": status})
        service.backtest_repo.save_result(
            run["id"],
            {
                "performance_metrics": {
                    "total_return": total_return, "sharpe_ratio": sharpe,
                }
            },
        )
        return run["id"]

    def test_side_by_side_with_metrics(self, service):
        r1 = self._make_run(service, "2026-01-01", "2026-06-30", 0.10, 1.2)
        r2 = self._make_run(service, "2026-01-01", "2026-06-30", 0.15, 1.5)
        out = service.compare_runs([r1, r2])
        assert [row["run_id"] for row in out["runs"]] == [r1, r2]
        assert out["runs"][1]["sharpe_ratio"] == 1.5
        assert out["range_warning"] is None

    def test_mismatched_ranges_warn(self, service):
        r1 = self._make_run(service, "2026-01-01", "2026-06-30", 0.1, 1.0)
        r2 = self._make_run(service, "2026-01-01", "2026-03-31", 0.2, 2.0)
        out = service.compare_runs([r1, r2])
        assert "区间不一致" in out["range_warning"]

    def test_pending_run_warned(self, service):
        r1 = self._make_run(service, "2026-01-01", "2026-06-30", 0.1, 1.0)
        r2 = self._make_run(service, "2026-01-01", "2026-06-30", 0.1, 1.0, status="running")
        out = service.compare_runs([r1, r2])
        assert str(r2) in out["range_warning"]

    def test_validates_count_and_existence(self, service):
        with pytest.raises(StrategyError):
            service.compare_runs([1])
        r1 = self._make_run(service, "2026-01-01", "2026-06-30", 0.1, 1.0)
        with pytest.raises(StrategyError):
            service.compare_runs([r1, 999])


class TestBuildDslConfig:
    def test_dsl_config_shape(self):
        config = build_strategy_config(
            dsl_filter="rank(momentum_20) > 0.8",
            dsl_order_by="rank(momentum_20) - rank(pe_percentile)",
            top_n=30,
            start_date="2026-01-01", end_date="2026-06-30",
            known_factors={"momentum_20", "pe_percentile"},
        )
        engine = config["engine_config"]
        assert engine["selection_method"] == "dsl_rule"
        assert engine["dsl"]["order_by"].startswith("rank(momentum_20)")
        assert engine["factor_list"] == ["momentum_20", "pe_percentile"]

    def test_dsl_mutually_exclusive_with_factor_ids(self):
        with pytest.raises(StrategyError, match="互斥"):
            build_strategy_config(
                factor_ids=["momentum_20"],
                dsl_order_by="momentum_20",
                known_factors={"momentum_20"},
            )

    def test_dsl_rejects_weights(self):
        with pytest.raises(StrategyError, match="weights"):
            build_strategy_config(
                dsl_order_by="momentum_20", weights={"momentum_20": 1.0},
                known_factors={"momentum_20"},
            )

    def test_dsl_unknown_factor_wrapped(self):
        with pytest.raises(StrategyError, match="DSL 非法"):
            build_strategy_config(
                dsl_order_by="nope + 1", known_factors={"momentum_20"},
            )

    def test_run_dsl_strategy_end_to_end(self, service, no_background_thread):
        config = build_strategy_config(
            dsl_filter="pe_percentile < 0.6",
            dsl_order_by="rank(momentum_20)",
            top_n=10,
            start_date="2026-01-01", end_date="2026-06-30",
            known_factors={"momentum_20", "pe_percentile"},
        )
        service.save_strategy("规则策略", config)
        run = service.run_strategy("规则策略")
        assert run["strategy_config"]["selection_method"] == "dsl_rule"
        thread_args = no_background_thread[0].args
        assert thread_args[0] == run["run_id"]
