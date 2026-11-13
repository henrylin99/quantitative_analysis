"""数据初始化编排器（DataInitOrchestrator）契约测试。

伪造 DataJobService（不触真实下载），验证：
- 分阶段计划与年数窗口参数透传（tushare 默认 1 年、财务默认 10 年）；
- 状态文件落盘（running→finished、steps 进度、history 归档）；
- 互斥：链路运行中重复 start 被拒。
"""

from __future__ import annotations

import time

import app.services.data_jobs.service as service_module
from app.services.data_jobs.init_orchestrator import (
    DataInitOrchestrator,
    _clamp_years,
    _years_window,
)


class _FakeRun:
    def __init__(self, run_id, status, progress=1.0, message="ok"):
        self.id = run_id
        self.status = status
        self.progress = progress
        self.progress_message = message


class _FakeService:
    submissions = []

    def submit(self, job_type, params=None):
        _FakeService.submissions.append((job_type, params or {}))
        return _FakeRun(len(_FakeService.submissions), "success")

    def get_run(self, run_id):
        return _FakeRun(run_id, "success")


def _wait_idle(orchestrator, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not orchestrator.status().get("running"):
            return
        time.sleep(0.1)


def test_years_window_and_clamp():
    win = _years_window(1)
    assert set(win) == {"start_date", "end_date"}
    assert win["end_date"] >= win["start_date"]
    # 1 年窗口 start 恰好是前推一年
    assert int(win["end_date"][:4]) - int(win["start_date"][:4]) == 1
    assert _clamp_years("abc", 1) == 1
    assert _clamp_years(99, 1) == 30
    assert _clamp_years(0, 10) == 1


def test_init_chain_runs_all_steps_with_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "DataJobService", _FakeService)
    _FakeService.submissions = []
    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    result = orchestrator.start(tushare_years=2, financial_years=10)
    assert result["ok"] is True

    _wait_idle(orchestrator)
    status = orchestrator.status()
    record = status["record"]
    assert record["ok"] is True
    assert record["message"] == "初始化完成"
    assert len(record["steps"]) == record["steps_total"]
    assert all(step["status"] == "success" for step in record["steps"].values())
    # 状态文件已落盘并归档 history
    assert status["running"] is False
    assert len(status["history"]) >= 1

    # 计划完整性 + 窗口参数
    submitted = {job: params for job, params in _FakeService.submissions}
    assert "stock_basic" in submitted and "stock_company" in submitted and "factor_compute" in submitted
    assert "adj_factor" in submitted  # 复权因子独立下载步
    assert submitted["stock_basic"] == {}  # 元数据作业不带窗口
    dh = submitted["daily_history_by_date"]
    assert int(dh["end_date"][:4]) - int(dh["start_date"][:4]) == 2
    fin = submitted["financial_fuyao"]
    assert int(fin["end_date"][:4]) - int(fin["start_date"][:4]) == 10


def test_init_rejects_when_chain_running(tmp_path, monkeypatch):
    import app.services.data_jobs.pipeline as pipeline_mod

    monkeypatch.setattr(service_module, "DataJobService", _FakeService)
    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    # 模拟 pipeline 链路占用互斥锁
    with pipeline_mod._chain_lock:
        pipeline_mod._chain_running.set()
        try:
            result = orchestrator.start()
            assert result["ok"] is False
        finally:
            pipeline_mod._chain_running.clear()
    _wait_idle(orchestrator, timeout=2.0)


def test_status_heals_stale_running_state(tmp_path):
    """服务重启遗留的 running 态（无 pid 无心跳）应被自愈为已中断。"""
    import json

    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    state_path = orchestrator.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "running": True,
        "record": {"started_at": "2026-11-13 09:00:00", "finished_at": None,
                   "ok": False, "message": None, "steps": {}},
        "history": [],
    }), encoding="utf-8")

    status = orchestrator.status()
    assert status["running"] is False
    assert "中断" in status["record"]["message"]
    assert status["record"]["finished_at"] is not None


def test_status_keeps_alive_owner_pid(tmp_path, monkeypatch):
    """pid 存活且心跳新鲜时不误判；pid 已死判为服务重启（多 worker 兼容）。"""
    import json
    import app.services.data_jobs.init_orchestrator as mod

    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    orchestrator.state_path.parent.mkdir(parents=True, exist_ok=True)

    def write_state(pid):
        orchestrator.state_path.write_text(json.dumps({
            "running": True,
            "record": {"pid": pid, "updated_at": mod._now(), "steps": {}},
            "history": [],
        }), encoding="utf-8")

    # 存活 pid（kill 探测不抛错）+ 新鲜心跳 → 不误判
    monkeypatch.setattr(mod.os, "kill", lambda pid, sig: None)
    write_state(12345)
    assert orchestrator.status()["running"] is True

    # 死 pid（kill 探测抛 OSError）→ 判服务重启
    monkeypatch.setattr(mod.os, "kill", lambda pid, sig: (_ for _ in ()).throw(OSError()))
    write_state(12345)
    status = orchestrator.status()
    assert status["running"] is False
    assert "重启" in status["record"]["message"]


def test_cancel_stops_chain_after_current_step(tmp_path, monkeypatch):
    """cancel 后：当前步骤标记 cancelled，后续步骤不再提交。"""
    monkeypatch.setattr(service_module, "DataJobService", _FakeService)
    _FakeService.submissions = []
    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    assert orchestrator.start()["ok"] is True
    # 立即请求中断（链路尚在第 1 步排队/运行）
    assert orchestrator.cancel()["ok"] is True
    _wait_idle(orchestrator, timeout=15.0)

    status = orchestrator.status()
    record = status["record"]
    assert status["running"] is False
    assert record["ok"] is False
    assert record["message"] == "已被用户中断"
    cancelled = [s for s in record["steps"].values() if s["status"] == "cancelled"]
    assert len(cancelled) >= 1
    # 中断后不应跑完全部步骤
    assert len(_FakeService.submissions) < len(record["steps_total"] and __import__(
        "app.services.data_jobs.init_orchestrator", fromlist=["INIT_PLAN"]).INIT_PLAN)


def test_cancel_rejects_when_not_running():
    orchestrator = DataInitOrchestrator()
    assert orchestrator.cancel()["ok"] is False


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-parquet-bytes")


def test_init_skips_steps_whose_data_exists(tmp_path, monkeypatch):
    """data/ 已存在的步骤应标记 skipped 不提交作业，只补缺失部分。"""
    monkeypatch.setattr(service_module, "DataJobService", _FakeService)
    _FakeService.submissions = []

    # 元数据文件 + 完整覆盖窗口的日线分区已存在
    _touch(tmp_path / "stock_basic.parquet")
    _touch(tmp_path / "stock_company.parquet")
    _touch(tmp_path / "stock_trade_calendar.parquet")
    win = _years_window(1)
    y, m, d = int(win["start_date"][:4]), int(win["start_date"][4:6]), int(win["start_date"][6:])
    _touch(tmp_path / "daily_history" / "daily" / f"year={y}" / f"month={m:02d}" / f"day={d:02d}" / "data.parquet")
    _touch(tmp_path / "daily_history" / "daily" / "year=2026" / "month=11" / "day=13" / "data.parquet")
    _touch(tmp_path / "adj_factor" / "daily" / f"year={y}" / f"month={m:02d}" / f"day={d:02d}" / "data.parquet")
    _touch(tmp_path / "adj_factor" / "daily" / "year=2026" / "month=11" / "day=13" / "data.parquet")
    _touch(tmp_path / "adj_factor" / "daily" / "year=2026" / "month=11" / "day=13" / "data.parquet")

    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    assert orchestrator.start()["ok"] is True
    _wait_idle(orchestrator)
    record = orchestrator.status()["record"]
    assert record["ok"] is True

    skipped = {s["job_type"] for s in record["steps"].values() if s["status"] == "skipped"}
    assert {"stock_basic", "stock_company", "trade_calendar", "daily_history_by_date", "adj_factor"} <= skipped
    for job_type in skipped:
        step = next(s for s in record["steps"].values() if s["job_type"] == job_type)
        assert "已有数据" in step["message"]

    submitted_jobs = {job for job, _ in _FakeService.submissions}
    assert not (skipped & submitted_jobs)  # 跳过的步不再提交
    assert "daily_basic" in submitted_jobs  # 缺失的步照常提交


def test_step_done_partial_coverage_not_skipped(tmp_path):
    """日线分区存在但不覆盖请求窗口（起点晚于窗口起点+60 天）→ 不跳过。"""
    _touch(tmp_path / "daily_history" / "daily" / "year=2026" / "month=06" / "day=01" / "data.parquet")
    orchestrator = DataInitOrchestrator(data_dir=str(tmp_path))
    win = _years_window(1)  # 起点 ~2025-11，现有数据 2026-06 起 → 覆盖不足
    done, evidence = orchestrator._step_done(
        "daily_history_by_date", {"start_date": win["start_date"], "end_date": win["end_date"]}, win)
    assert done is False
    assert "分区" in evidence
