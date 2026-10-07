"""数据链路编排与新鲜度巡检测试。"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app.services.data_jobs.pipeline import (
    DataFreshnessService,
    DataPipelineOrchestrator,
    _latest_hive_date,
    _latest_trade_date_partition,
    load_trade_calendar,
)


def _make_calendar(path, open_days_yyyymmdd):
    pd.DataFrame({
        "cal_date": open_days_yyyymmdd,
        "is_open": [1] * len(open_days_yyyymmdd),
    }).to_parquet(path)


class TestPartitionScanners:
    def test_hive_layout(self, tmp_path):
        d = tmp_path / "daily_history/daily/year=2026/month=10"
        (d / "day=09").mkdir(parents=True)
        (d / "day=10").mkdir(parents=True)
        assert _latest_hive_date(tmp_path / "daily_history/daily") == "2026-10-10"

    def test_trade_date_layout(self, tmp_path):
        d = tmp_path / "ml_factor_state/factor_values"
        (d / "trade_date=2026-10-09").mkdir(parents=True)
        (d / "trade_date=2026-10-10").mkdir(parents=True)
        assert _latest_trade_date_partition(d) == "2026-10-10"

    def test_missing_dir_returns_none(self, tmp_path):
        assert _latest_hive_date(tmp_path / "nope") is None
        assert _latest_trade_date_partition(tmp_path / "nope") is None


class TestFreshness:
    def _prepare(self, tmp_path, latest_map):
        for rel, day in latest_map.items():
            (tmp_path / rel / f"year={day[:4]}" / f"month={day[5:7]}" / f"day={day[8:]}").mkdir(parents=True)
        # 日历：今天 + 前两天为交易日（相对当前日期，避免硬编码撞日期翻转）
        today = datetime.now()
        open_days = [(today - pd.Timedelta(days=k)).strftime("%Y%m%d") for k in (2, 1, 0)]
        _make_calendar(tmp_path / "stock_trade_calendar.parquet", open_days)
        return today.strftime("%Y-%m-%d")

    def test_lag_computed(self, tmp_path):
        today = self._prepare(tmp_path, {
            "daily_history/daily": datetime.now().strftime("%Y-%m-%d"),
            "moneyflow/daily": (datetime.now() - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        })
        st = DataFreshnessService(data_dir=str(tmp_path)).status()
        assert st["expected_date"] == today
        by_name = {r["table"]: r for r in st["tables"]}
        assert by_name["daily_history"]["lag_trading_days"] == 0
        assert by_name["daily_history"]["ok"] is True
        assert by_name["moneyflow"]["lag_trading_days"] == 1
        assert by_name["moneyflow"]["ok"] is False
        assert not st["all_fresh"]
        assert "moneyflow" in st["lagged_tables"]
        assert "daily_history" not in st["lagged_tables"]

    def test_all_fresh(self, tmp_path):
        # 巡检清单里的全部表 + factor_values 都建到最新 → all_fresh
        today = datetime.now().strftime("%Y-%m-%d")
        latest_map = {rel: today for rel in
                      ("daily_history/daily", "daily_basic/daily", "stk_factor/daily",
                       "moneyflow/daily", "cyq_perf/daily", "adj_factor/daily")}
        self._prepare(tmp_path, latest_map)
        (tmp_path / "ml_factor_state/factor_values" / f"trade_date={today}").mkdir(parents=True)
        st = DataFreshnessService(data_dir=str(tmp_path)).status()
        assert st["all_fresh"]
        assert st["lagged_tables"] == []

    def test_missing_table_lags(self, tmp_path):
        # 只有日历，无任何数据分区 → 全部滞后
        _make_calendar(tmp_path / "stock_trade_calendar.parquet", ["20261008"])
        st = DataFreshnessService(data_dir=str(tmp_path)).status()
        assert not st["all_fresh"]
        assert st["tables"][0]["latest_date"] is None

    def test_calendar_formats_normalized(self, tmp_path):
        _make_calendar(tmp_path / "stock_trade_calendar.parquet", ["20261008"])
        days = load_trade_calendar(tmp_path)
        assert days == ["2026-10-08"]


class TestChain:
    def _patch_job_service(self, monkeypatch, fail_on=None):
        """打桩 DataJobService：submit 记录顺序，get_run 返回终态。"""
        submitted = []

        class _Run:
            def __init__(self, rid):
                self.id = rid

        class _Final:
            def __init__(self, status):
                self.status = status
                self.progress_message = status

        class _FakeSvc:
            def submit(self, job_type, params=None):
                submitted.append(job_type)
                return _Run(len(submitted))

            def get_run(self, run_id):
                job = submitted[run_id - 1]
                status = "failed" if job == fail_on else "success"
                return _Final(status)

        import app.services.data_jobs.pipeline as pl
        monkeypatch.setattr(pl, "DataJobService", _FakeSvc, raising=False)
        # pipeline.run_chain 内部是局部 import，需同时打桩 service 模块
        import app.services.data_jobs.service as svc_mod
        monkeypatch.setattr(svc_mod, "DataJobService", _FakeSvc)
        return submitted

    def test_chain_runs_in_order_and_aborts_on_failure(self, tmp_path, monkeypatch):
        submitted = self._patch_job_service(monkeypatch, fail_on="moneyflow")
        orch = DataPipelineOrchestrator(data_dir=str(tmp_path))
        result = orch.run_chain(
            job_types=["trade_calendar", "daily_history_by_date", "moneyflow", "stk_factor"])
        assert result["ok"] is False
        assert submitted == ["trade_calendar", "daily_history_by_date", "moneyflow"]
        assert result["steps"][-1]["status"] == "failed"
        assert "moneyflow" in result["message"]

    def test_chain_success(self, tmp_path, monkeypatch):
        submitted = self._patch_job_service(monkeypatch)
        orch = DataPipelineOrchestrator(data_dir=str(tmp_path))
        result = orch.run_chain(job_types=["trade_calendar", "daily_basic"])
        assert result["ok"] is True
        assert submitted == ["trade_calendar", "daily_basic"]
        assert len(orch.list_runs()) == 1

    def test_non_trading_day_skips(self, tmp_path, monkeypatch):
        submitted = self._patch_job_service(monkeypatch)
        _make_calendar(tmp_path / "stock_trade_calendar.parquet", ["20260101"])  # 今天不在其中
        orch = DataPipelineOrchestrator(data_dir=str(tmp_path))
        result = orch.run_chain(job_types=["trade_calendar"])
        assert result["ok"] is True
        assert submitted == []  # 一个作业都没提交
        assert result["is_trading_day"] is False


def test_registry_dependency_names_resolve():
    """回归：所有作业的 dependencies 必须能在注册表解析（曾出现幽灵 adj_factor）。"""
    from app.services.data_jobs.registry import JobRegistry

    registry = JobRegistry()
    known = {j.job_type for j in registry.list_jobs()}
    for job in registry.list_jobs():
        for dep in job.dependencies:
            assert dep in known, f"{job.job_type} 依赖了不存在的作业: {dep}"
