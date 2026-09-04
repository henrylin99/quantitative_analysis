"""缺口回补解析与 DailyFetchJob 骨架合约。"""
import pandas as pd
import pytest

from app.utils import parquet_job_helpers

pytestmark = pytest.mark.module_data_jobs


class _FakeReader:
    """交易日历：6/3、6/4、6/8 开市，6/5 休市。"""

    def get_trade_calendar(self):
        return pd.DataFrame(
            [
                {"exchange": "SSE", "cal_date": "20260603", "is_open": 1},
                {"exchange": "SSE", "cal_date": "20260604", "is_open": 1},
                {"exchange": "SSE", "cal_date": "20260605", "is_open": 0},
                {"exchange": "SSE", "cal_date": "20260608", "is_open": 1},
            ]
        )


def _patch_reader(monkeypatch):
    monkeypatch.setattr(parquet_job_helpers, "ParquetDataReader", lambda: _FakeReader())


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("DATA_JOB_START_DATE", "DATA_JOB_END_DATE", "DATA_JOB_TRADE_DATE",
                "DATA_JOB_FULL_REFRESH", "DATA_JOB_MAX_GAP_FILL"):
        monkeypatch.delenv(key, raising=False)


def test_gap_fill_returns_missing_dates_within_local_range(monkeypatch, tmp_path):
    _patch_reader(monkeypatch)
    # 本地已有 6/3 与 6/8，缺 6/4
    for day in ("20260603", "20260608"):
        partition = tmp_path / "t" / "year=2026" / "month=06" / f"day={day[6:]}"
        partition.mkdir(parents=True)

    dates, full_refresh = parquet_job_helpers.resolve_trade_dates_with_gap_fill("t", data_dir=str(tmp_path))

    assert full_refresh is False
    assert dates == ["20260604"]


def test_gap_fill_ignores_dates_before_first_partition(monkeypatch, tmp_path):
    """最早分区之前的日期属于历史基线，不自动回补。"""
    _patch_reader(monkeypatch)
    partition = tmp_path / "t" / "year=2026" / "month=06" / "day=04"
    partition.mkdir(parents=True)

    dates, _ = parquet_job_helpers.resolve_trade_dates_with_gap_fill("t", data_dir=str(tmp_path))

    assert dates == ["20260608"]


def test_gap_fill_respects_explicit_env(monkeypatch, tmp_path):
    """显式传参时与 resolve_trade_dates 行为一致，不做差集。"""
    _patch_reader(monkeypatch)
    monkeypatch.setenv("DATA_JOB_START_DATE", "20260603")
    monkeypatch.setenv("DATA_JOB_END_DATE", "20260603")
    (tmp_path / "t" / "year=2026" / "month=06" / "day=03").mkdir(parents=True)

    dates, _ = parquet_job_helpers.resolve_trade_dates_with_gap_fill("t", data_dir=str(tmp_path))

    assert dates == ["20260603"]


def test_gap_fill_no_local_table_falls_back_to_latest_only(monkeypatch, tmp_path):
    _patch_reader(monkeypatch)

    dates, _ = parquet_job_helpers.resolve_trade_dates_with_gap_fill("missing_table", data_dir=str(tmp_path))

    assert dates == ["20260608"]


def test_gap_fill_caps_single_run(monkeypatch, tmp_path):
    """超过 DATA_JOB_MAX_GAP_FILL 时从旧往新截断，防止一次烧光 API 配额。"""
    _patch_reader(monkeypatch)
    monkeypatch.setenv("DATA_JOB_MAX_GAP_FILL", "1")
    (tmp_path / "t" / "year=2026" / "month=06" / "day=03").mkdir(parents=True)

    dates, _ = parquet_job_helpers.resolve_trade_dates_with_gap_fill("t", data_dir=str(tmp_path))

    assert dates == ["20260608"]


class _FlakyJob(parquet_job_helpers.DailyFetchJob):
    """前 N-1 次调用抛异常的假作业。"""

    job_name = "flaky"
    rel_table = "flaky/daily"
    rate_limit_seconds = 0.0
    max_retries = 3

    def __init__(self, api=None, fail_times=1):
        super().__init__(api=api)
        self.fail_times = fail_times
        self.calls = []

    def fetch_one(self, trade_date):
        self.calls.append(trade_date)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("网络抖动")
        return pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": trade_date, "close": 1.0}])


def test_daily_fetch_job_retries_and_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(parquet_job_helpers.time, "sleep", lambda *_: None)
    _patch_reader(monkeypatch)
    monkeypatch.setenv("DATA_JOB_TRADE_DATE", "20260604")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # 落盘必须进沙箱，不能写真实 data/
    job = _FlakyJob(fail_times=1)

    saved = job.run()

    assert saved == 1
    assert len(job.calls) == 2, "失败后应立刻重试"
    frame = pd.read_parquet(tmp_path / "flaky" / "daily" / "year=2026" / "month=06" / "day=04" / "data.parquet")
    assert len(frame) == 1


def test_daily_fetch_job_exits_nonzero_when_all_retries_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(parquet_job_helpers.time, "sleep", lambda *_: None)
    _patch_reader(monkeypatch)
    monkeypatch.setenv("DATA_JOB_TRADE_DATE", "20260604")
    job = _FlakyJob(fail_times=99)

    with pytest.raises(SystemExit) as excinfo:
        job.run()

    assert excinfo.value.code == 1
    assert job.calls and len(job.calls) == job.max_retries
    assert not (tmp_path / "flaky").exists() or not list((tmp_path / "flaky").rglob("data.parquet"))
