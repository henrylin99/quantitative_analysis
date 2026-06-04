from pathlib import Path

import pandas as pd

from app.services.data_reader import ParquetDataReader


def test_data_reader_can_expose_minute_reader(tmp_path):
    base = Path(tmp_path) / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    base.mkdir(parents=True)
    pd.DataFrame(
        [{"ts_code": "000001.SZ", "period_type": "1min", "datetime": "2026-06-04T09:31:00", "close": 10.1}]
    ).to_parquet(base / "data.parquet", index=False)

    reader = ParquetDataReader(data_dir=str(tmp_path))
    minute_reader = reader.get_minute_reader()

    data = minute_reader.get_data(ts_code="000001.SZ", period_type="1min")
    assert len(data) == 1
    assert data.iloc[0]["close"] == 10.1
