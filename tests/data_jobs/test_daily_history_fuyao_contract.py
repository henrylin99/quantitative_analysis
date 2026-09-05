"""daily_history_fuyao 合约测试：脚本主流程、schema 同构、注册表元数据。

数据源契约：fuyao 是 daily_history/daily 表的可选生产者，产出必须与
ParquetDataReader.STANDARD_COLUMNS["daily"] 完全兼容。
"""

import os
from pathlib import Path

import pandas as pd
import pytest

from app.services.data_jobs.registry import JobRegistry
from app.services.data_reader import ParquetDataReader
from app.utils import daily_history_fuyao
from app.utils.data_sources.fuyao_normalize import DAILY_COLUMNS

pytestmark = pytest.mark.module_data_jobs


def _fake_fetcher(monkeypatch, frames):
    class _FakeFetcher:
        def __init__(self, *args, **kwargs):
            pass

        def fetch_dates(self, trade_dates):
            return {d: frames[d] for d in trade_dates if d in frames}

    monkeypatch.setattr(daily_history_fuyao, "FuyaoDailyFetcher", _FakeFetcher)


def _sample_frame(ts_code="000001.SZ", trade_date="20260904"):
    return pd.DataFrame([
        {
            "ts_code": ts_code, "trade_date": trade_date, "open": 11.86, "high": 12.0,
            "low": 11.85, "close": 11.89, "pre_close": 11.88, "change": 0.01,
            "pct_chg": 0.0842, "vol": 814372.0, "amount": 969948.44,
        }
    ])


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_JOB_TRADE_DATE", "20260904")
    for key in ("DATA_JOB_START_DATE", "DATA_JOB_END_DATE", "DATA_JOB_FULL_REFRESH"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def test_main_writes_partition_with_standard_schema(data_dir, monkeypatch):
    _fake_fetcher(monkeypatch, {"20260904": _sample_frame()})

    exit_code = daily_history_fuyao.main()

    assert exit_code == 0
    partition = data_dir / "daily_history" / "daily" / "year=2026" / "month=09" / "day=04"
    assert (partition / "data.parquet").exists()


def test_written_data_readable_via_parquet_reader(data_dir, monkeypatch):
    """读取侧对数据源无感知：ParquetDataReader 按标准列读出 fuyao 产出。"""
    _fake_fetcher(monkeypatch, {"20260904": _sample_frame()})
    daily_history_fuyao.main()

    reader = ParquetDataReader(data_dir=str(data_dir))
    df = reader.get_daily(ts_codes=["000001.SZ"], start_date="20260904", end_date="20260904")
    assert not df.empty
    assert set(DAILY_COLUMNS).issubset(set(df.columns))
    row = df[df["ts_code"] == "000001.SZ"].iloc[0]
    assert row["close"] == pytest.approx(11.89)
    assert row["vol"] == pytest.approx(814372.0)


def test_main_fails_when_trade_date_missing(data_dir, monkeypatch, capsys):
    _fake_fetcher(monkeypatch, {})  # 数据源没有返回任何日期

    exit_code = daily_history_fuyao.main()

    assert exit_code == 1
    assert "20260904" in capsys.readouterr().out


def test_main_noop_without_trade_dates(data_dir, monkeypatch):
    monkeypatch.delenv("DATA_JOB_TRADE_DATE", raising=False)
    _fake_fetcher(monkeypatch, {"20260904": _sample_frame()})

    # 无交易日历、无显式参数 → 无可拉取日期，直接成功返回
    assert daily_history_fuyao.main() == 0


def test_registry_metadata_fuyao_source():
    registry = JobRegistry()
    job = registry.get_job("daily_history_fuyao")
    assert job.source_name == "fuyao"
    assert job.supports_incremental is True
    assert "trade_calendar" in job.dependencies
    assert "daily_history_fuyao" in registry._visible_job_types
    # 与 tushare 版互为同表生产者，两者都在册
    assert registry.get_job("daily_history_by_date").source_name == "tushare"
