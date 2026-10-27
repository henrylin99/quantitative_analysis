"""策略守护：三态状态机、登记/删除/复活、history 落盘、跳过条件。"""

from __future__ import annotations

import json

import pytest

from app.services.strategy_guardian_service import (
    STATUS_HEALTHY,
    STATUS_RETIRED,
    STATUS_WATCH,
    StrategyGuardianService,
    run_daily_guardian,
)


class _FakeOptimizer:
    """按策略名返回预设近期超额，验证状态迁移本身。"""

    def __init__(self, excess_by_signal=None, default=0.02):
        self.excess_by_signal = excess_by_signal or {}
        self.default = default

    def chip_threshold_optimize(self, months, signal, horizon, grid):
        excess = self.excess_by_signal.get(signal, self.default)
        return {"grid_results": [{"params": grid, "excess": excess}]}


@pytest.fixture()
def isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield tmp_path


def _register(svc, **kw):
    defaults = dict(name="t", kind="chip_signal", params={"squeeze_winner_min": 60.0},
                    signal="resonance")
    defaults.update(kw)
    return svc.register(**defaults)


def test_register_list_remove_roundtrip(isolated_dir):
    svc = StrategyGuardianService(_FakeOptimizer())
    rec = _register(svc)
    assert rec["status"] == STATUS_HEALTHY
    assert [s["id"] for s in svc.list_strategies()] == [rec["id"]]
    assert "removed" in svc.remove(rec["id"])
    assert svc.list_strategies() == []
    assert "error" in svc.remove(rec["id"])


def test_register_rejects_unknown_kind(isolated_dir):
    svc = StrategyGuardianService(_FakeOptimizer())
    assert "error" in _register(svc, kind="magic")


def test_healthy_to_watch_to_healthy(isolated_dir):
    opt = _FakeOptimizer(default=-0.01)  # 低于 watch 线 0
    svc = StrategyGuardianService(opt)
    rec = _register(svc)
    out = svc.run_daily(push=False)
    assert out["results"][0]["status"] == STATUS_WATCH
    assert out["status_changes"][0]["prev_status"] == STATUS_HEALTHY

    opt.default = 0.05  # 恢复
    out = svc.run_daily(push=False)
    assert out["results"][0]["status"] == STATUS_HEALTHY
    assert svc.list_strategies()[0]["watch_days"] == 0


def test_watch_consecutive_days_retire(isolated_dir):
    opt = _FakeOptimizer(default=-0.01)
    svc = StrategyGuardianService(opt)
    rec = _register(svc, max_watch_days=3)
    svc.run_daily(push=False)  # → watch, watch_days=1
    svc.run_daily(push=False)  # watch_days=2
    out = svc.run_daily(push=False)  # watch_days=3 → retired
    assert out["results"][0]["status"] == STATUS_RETIRED


def test_retire_line_direct(isolated_dir):
    opt = _FakeOptimizer(default=-0.10)  # 低于 retire 线 -0.05
    svc = StrategyGuardianService(opt)
    _register(svc)
    out = svc.run_daily(push=False)
    assert out["results"][0]["status"] == STATUS_RETIRED


def test_retired_is_sticky_and_resume_to_watch(isolated_dir):
    opt = _FakeOptimizer(default=-0.10)
    svc = StrategyGuardianService(opt)
    rec = _register(svc)
    svc.run_daily(push=False)
    opt.default = 0.05
    svc.run_daily(push=False)  # retired 不自动复活
    assert svc.list_strategies()[0]["status"] == STATUS_RETIRED
    resumed = svc.resume(rec["id"])
    assert resumed["status"] == STATUS_WATCH


def test_baseline_and_history_recorded(isolated_dir):
    svc = StrategyGuardianService(_FakeOptimizer(default=0.03))
    rec = _register(svc)
    svc.run_daily(push=False)
    stored = svc.list_strategies()[0]
    assert stored["baseline_excess"] == 0.03
    assert stored["last_excess"] == 0.03
    hist = svc.history(rec["id"])
    assert len(hist) == 1 and hist[0]["id"] == rec["id"]


def test_eval_failure_keeps_status(isolated_dir):
    class _Broken:
        def chip_threshold_optimize(self, **kw):
            return {"error": "无数据"}

    svc = StrategyGuardianService(_Broken())
    _register(svc)
    out = svc.run_daily(push=False)
    assert out["results"][0]["excess"] is None
    assert out["results"][0]["status"] == STATUS_HEALTHY


def test_run_daily_guardian_skips_when_empty(isolated_dir, monkeypatch):
    monkeypatch.delenv("STRATEGY_GUARDIAN_ENABLED", raising=False)
    assert run_daily_guardian() == {"skipped": "no_registered_strategies"}


def test_run_daily_guardian_disabled(isolated_dir, monkeypatch):
    svc = StrategyGuardianService(_FakeOptimizer())
    _register(svc)
    monkeypatch.setenv("STRATEGY_GUARDIAN_ENABLED", "0")
    assert run_daily_guardian() == {"skipped": "disabled"}


def test_run_daily_guardian_weekend_skip(isolated_dir, monkeypatch):
    import datetime as _dt

    import app.services.strategy_guardian_service as mod

    svc = StrategyGuardianService(_FakeOptimizer())
    _register(svc)

    class _Saturday(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 31, 19, 0)  # 周六

    assert _dt.datetime(2026, 10, 31).weekday() == 5
    monkeypatch.setattr(mod, "datetime", _Saturday)
    assert run_daily_guardian() == {"skipped": "weekend"}
