import pandas as pd
import pytest

from app.utils import parquet_job_helpers

pytestmark = pytest.mark.module_data_jobs


class _FakeReader:
    def get_trade_calendar(self):
        return pd.DataFrame(
            [
                {"exchange": "SSE", "cal_date": "20260603", "is_open": 1},
                {"exchange": "SSE", "cal_date": "20260604", "is_open": 1},
                {"exchange": "SSE", "cal_date": "20260605", "is_open": 0},
            ]
        )


def test_resolve_trade_dates_uses_trade_calendar_for_new_open_dates(monkeypatch):
    monkeypatch.setenv("DATA_JOB_START_DATE", "2026-06-04")
    monkeypatch.setenv("DATA_JOB_END_DATE", "2026-06-04")
    monkeypatch.delenv("DATA_JOB_TRADE_DATE", raising=False)
    monkeypatch.delenv("DATA_JOB_FULL_REFRESH", raising=False)
    monkeypatch.setattr(parquet_job_helpers, "ParquetDataReader", lambda: _FakeReader())

    trade_dates, full_refresh = parquet_job_helpers.resolve_trade_dates()

    assert trade_dates == ["20260604"]
    assert full_refresh is False
