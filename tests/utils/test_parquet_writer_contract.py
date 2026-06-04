from pathlib import Path

import pandas as pd

from app.utils.parquet_writer import save_to_parquet


def test_save_to_parquet_writes_hive_style_year_month_day_partition(tmp_path):
    frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "close": 10.5},
            {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "close": 11.5},
        ]
    )

    written = save_to_parquet(frame, "2024-06-04", "daily_history/daily", str(tmp_path))

    assert written == 2
    parquet_path = (
        Path(tmp_path)
        / "daily_history"
        / "daily"
        / "year=2024"
        / "month=06"
        / "day=04"
        / "data.parquet"
    )
    assert parquet_path.is_file()

