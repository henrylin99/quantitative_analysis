"""上一轮质量修复的合约测试：孤儿 run 清理、模型缓存失效、inf 清洗、
rolling 预热窗、求解器回退。

对应审查指出的 8 项零测试高风险修复，逐项钉住行为。
"""
import importlib
import os
import sys
import time

import cvxpy
import joblib
import numpy as np
import pandas as pd
import pytest

from app.services.factor_engine import FactorEngine
from app.services.factor_expression_engine import FactorExpressionEngine
from app.services.parquet_state_store import BacktestRepository, ParquetStateStore
import app.tasks.backtest_tasks as backtest_tasks

if not hasattr(cvxpy, "installed_solvers"):
    # conftest 为 minimal CI 注入的空桩占据了 sys.modules；本模块的求解器
    # 用例验证真实路径，恢复真实库并重载绑定过桩的被测模块
    del sys.modules["cvxpy"]
    cvxpy = importlib.import_module("cvxpy")
    if "app.services.portfolio_optimizer" in sys.modules:
        importlib.reload(sys.modules["app.services.portfolio_optimizer"])
from app.services.portfolio_optimizer import PortfolioOptimizer

pytestmark = pytest.mark.module_backtest


class _PicklableModelV1:
    """模块级定义：joblib.dump 需要可按限定名 pickle 的类。"""

    tag = "v1"

    def predict(self, X):
        return [0.0] * len(X)


class _PicklableModelV2:
    tag = "v2"

    def predict(self, X):
        return [1.0] * len(X)


# ---------------------------------------------------------------------------
# 孤儿 run 清理：注册表判活
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_active_registry():
    """注册表是模块级全局态，测试间必须复位。"""
    with backtest_tasks._active_lock:
        saved_ids = set(backtest_tasks._active_run_ids)
        saved_flag = backtest_tasks._orphans_reaped_since_boot
        backtest_tasks._active_run_ids = set()
        backtest_tasks._orphans_reaped_since_boot = False
    yield
    with backtest_tasks._active_lock:
        backtest_tasks._active_run_ids = saved_ids
        backtest_tasks._orphans_reaped_since_boot = saved_flag


def _make_run(repo, status):
    run = repo.create_run({}, "2026-01-01", "2026-06-01", 1000000.0, "monthly")
    repo.update_summary(run["id"], {"status": status})
    return run["id"]


def test_reap_stale_runs_never_kills_active_runs(tmp_path):
    """在册（线程存活）的 run 即使跑了很久也绝不能被清理。"""
    repo = BacktestRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    active_id = _make_run(repo, "running")
    orphan_id = _make_run(repo, "running")
    done_id = _make_run(repo, "succeeded")

    backtest_tasks.mark_run_active(active_id)
    reaped = repo.reap_stale_runs(active_run_ids={active_id})

    reaped_ids = {r["id"] for r in reaped}
    assert reaped_ids == {orphan_id}
    assert repo.get_run(active_id)["summary"]["status"] == "running"
    assert repo.get_run(orphan_id)["summary"]["status"] == "failed"
    assert repo.get_run(done_id)["summary"]["status"] == "succeeded"


def test_reap_stale_runs_skips_queued_orphans_marked_failed(tmp_path):
    """queued 状态的孤儿同样要清理（提交后线程未起就崩了的场景）。"""
    repo = BacktestRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    queued_id = _make_run(repo, "queued")

    reaped = repo.reap_stale_runs(active_run_ids=set())

    assert {r["id"] for r in reaped} == {queued_id}
    assert repo.get_run(queued_id)["summary"]["status"] == "failed"


def test_registry_roundtrip_and_orphan_reap_once(tmp_path, monkeypatch):
    """mark/clear/is_run_active 语义；reap_orphans_once 只在进程首次调用时落盘。"""
    monkeypatch.setattr(backtest_tasks, "_build_repo", lambda: BacktestRepository(
        ParquetStateStore(base_dir=str(tmp_path / "state"))
    ))

    assert not backtest_tasks.is_run_active(7)
    backtest_tasks.mark_run_active(7)
    assert backtest_tasks.is_run_active(7)
    backtest_tasks.clear_run_active(7)
    assert not backtest_tasks.is_run_active(7)

    repo = backtest_tasks._build_repo()
    orphan = _make_run(repo, "running")
    backtest_tasks.mark_run_active(999)  # 另一个存活 run，不在本库中

    assert len(backtest_tasks.reap_orphans_once()) == 1
    assert repo.get_run(orphan)["summary"]["status"] == "failed"
    # 第二次调用是 no-op：孤儿只可能来自上个进程，无需反复全表扫描
    assert backtest_tasks.reap_orphans_once() == []


# ---------------------------------------------------------------------------
# ML 模型缓存按磁盘 mtime 失效
# ---------------------------------------------------------------------------


def test_load_model_reloads_when_disk_file_changes(tmp_path):
    from app.services.ml_models import MLModelManager

    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    manager = MLModelManager(state_store=store)
    manager.model_dir = str(tmp_path / "models")
    os.makedirs(manager.model_dir, exist_ok=True)

    model_path = os.path.join(manager.model_dir, "retrain.pkl")
    joblib.dump(_PicklableModelV1(), model_path)
    assert manager.load_model("retrain")
    assert manager.models["retrain"].tag == "v1"

    # 模拟外部进程重训落盘：mtime 变化后必须重载，不能一直用旧模型
    time.sleep(0.02)
    joblib.dump(_PicklableModelV2(), model_path)
    assert manager.load_model("retrain")
    assert manager.models["retrain"].tag == "v2"

    # 无变化时命中缓存（不再重复 joblib.load）
    assert manager.load_model("retrain")
    assert manager.models["retrain"].tag == "v2"


def test_load_model_keeps_memory_only_model_without_disk_file(tmp_path):
    """仅存在于内存的模型（如测试注入）不因磁盘无文件而被清掉。"""
    from app.services.ml_models import MLModelManager

    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.model_dir = str(tmp_path / "models")

    class Fake:
        tag = "mem"

    manager.models["mem_only"] = Fake()
    assert manager.load_model("mem_only")
    assert manager.models["mem_only"].tag == "mem"


# ---------------------------------------------------------------------------
# inf 清洗：内置 + 自定义因子两条路径
# ---------------------------------------------------------------------------


def test_finalize_factor_result_cleans_inf():
    df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
            "trade_date": pd.to_datetime(["2026-06-04"] * 3),
            "value": [1.0, np.inf, -np.inf],
        }
    )
    out = FactorEngine._finalize_factor_result(df, "value", "money_flow_strength")

    assert len(out) == 1
    assert np.isfinite(out["factor_value"]).all()


class _StubReader:
    """只为 _calculate_custom_factor 提供最小行情面。"""

    def __init__(self, frame):
        self._frame = frame

    def get_return_prices(self, ts_codes=None, start_date=None, end_date=None, price_fields=None):
        return self._frame.copy()


def test_custom_factor_cleans_inf_from_division_by_zero():
    """自定义公式除零（1/close，close=0）产生的 inf 不得入库。"""
    dates = pd.date_range("2026-06-01", periods=4).strftime("%Y-%m-%d")
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 4,
            "trade_date": dates,
            "open": [1.0] * 4,
            "high": [1.0] * 4,
            "low": [1.0] * 4,
            "close": [0.0, 10.0, 10.0, 10.0],  # 第一天除零 → inf
            "pre_close": [0.0, 0.0, 10.0, 10.0],
        }
    )

    engine = FactorEngine()
    engine.data_reader = _StubReader(frame)
    engine.factor_definitions["inv_close"] = {"factor_formula": "1/close"}
    out = engine._calculate_custom_factor("inv_close", ["000001.SZ"], dates[0], dates[-1])

    assert not out.empty
    assert np.isfinite(out["factor_value"]).all()
    assert len(out) == 3  # inf 行被清洗，不占位


# ---------------------------------------------------------------------------
# rolling 预热窗：字面量、关键字、取最大
# ---------------------------------------------------------------------------


def test_extract_max_rolling_window_supports_positional_and_keyword():
    engine = FactorExpressionEngine()

    assert engine.extract_max_rolling_window("close.rolling(250).mean()") == 250
    assert engine.extract_max_rolling_window("close.rolling(window=300).mean()") == 300
    assert (
        engine.extract_max_rolling_window(
            "close.rolling(5).mean() - close.rolling(window=120).std()"
        )
        == 120
    )
    assert engine.extract_max_rolling_window("close.pct_change(20)") is None
    assert engine.extract_max_rolling_window("bad formula (((") is None


def test_custom_factor_expands_preheat_window_for_large_rolling():
    """rolling 窗口大于默认回看时，读取窗口必须外推，否则因子前段全 NaN。"""
    requested = {}

    class _CapturingReader(_StubReader):
        def get_return_prices(self, ts_codes=None, start_date=None, end_date=None, price_fields=None):
            requested["start_date"] = start_date
            return super().get_return_prices(ts_codes, start_date, end_date, price_fields)

    dates = pd.date_range("2026-06-01", periods=400).strftime("%Y-%m-%d")
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 400,
            "trade_date": dates,
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": np.linspace(10, 20, 400),
            "pre_close": 10.0,
        }
    )

    engine = FactorEngine()
    engine.data_reader = _CapturingReader(frame)
    engine.factor_definitions["long_ma"] = {"factor_formula": "close.rolling(250).mean()"}
    engine._calculate_custom_factor("long_ma", ["000001.SZ"], dates[-1], dates[-1])

    from datetime import datetime, timedelta

    expected_start = (
        datetime.strptime(dates[-1], "%Y-%m-%d")
        - timedelta(days=int(250 * FactorEngine.CALENDAR_DAYS_PER_TRADING_DAY) + FactorEngine.PREHEAT_BUFFER_DAYS)
    ).strftime("%Y-%m-%d")
    assert requested["start_date"] == expected_start


# ---------------------------------------------------------------------------
# 均值方差求解器：ECOS 移除后按安装情况回退
# ---------------------------------------------------------------------------


def test_resolve_qp_solver_prefers_installed_solver():
    import cvxpy as cp

    solver = PortfolioOptimizer._resolve_qp_solver()
    installed = set(cp.installed_solvers())

    if "CLARABEL" in installed:
        assert solver is cp.CLARABEL
    else:
        # 环境没有任何偏好求解器时退回 cvxpy 默认，绝不指向已移除的 ECOS
        assert solver is None or solver is not getattr(cp, "ECOS", object())


def test_mean_variance_optimization_actually_solves():
    rng = np.random.default_rng(42)
    codes = [f"{i:06d}.SZ" for i in range(1, 9)]
    returns = pd.Series(rng.normal(0.001, 0.02, 8), index=codes)
    cov = pd.DataFrame(np.eye(8) * 0.02 ** 2, index=codes, columns=codes)

    weights = PortfolioOptimizer()._mean_variance_optimization(returns, cov, {})

    assert weights is not None
    assert weights.notna().all()
    assert weights.sum() == pytest.approx(1.0)
