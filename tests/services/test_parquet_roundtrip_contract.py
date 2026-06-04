import pandas as pd
import pytest

from app.services.data_reader import ParquetDataReader
from app.utils.parquet_writer import save_partitioned_parquet

pytestmark = pytest.mark.module_data_jobs


def test_daily_partition_roundtrip_preserves_trade_date(tmp_path):
    frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "close": 10.5},
            {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "close": 11.5},
        ]
    )

    saved = save_partitioned_parquet(frame, "trade_date", "daily_history/daily", str(tmp_path))
    assert saved == 2

    reader = ParquetDataReader(data_dir=str(tmp_path))
    loaded = reader.get_daily(ts_codes=["000001.SZ", "000002.SZ"])

    assert "trade_date" in loaded.columns
    assert loaded["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-06-04", "2024-06-04"]


def test_quarterly_partition_roundtrip_preserves_end_date(tmp_path):
    frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "end_date": "2024-03-31", "total_revenue": 100.0},
            {"ts_code": "000001.SZ", "end_date": "2024-06-30", "total_revenue": 120.0},
        ]
    )

    saved = save_partitioned_parquet(frame, "end_date", "income_statement", str(tmp_path))
    assert saved == 2

    reader = ParquetDataReader(data_dir=str(tmp_path))
    loaded = reader.get_income_statement(["000001.SZ"])

    assert "end_date" in loaded.columns
    assert loaded["end_date"].tolist() == ["2024-06-30", "2024-03-31"]
