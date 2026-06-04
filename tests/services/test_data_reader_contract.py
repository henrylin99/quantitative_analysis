from pathlib import Path

import pandas as pd

from app.services.data_reader import ParquetDataReader


def _write_partition(root: Path, year: str, month: str, day: str, frame: pd.DataFrame) -> None:
    partition_dir = root / "daily_history" / "daily" / f"year={year}" / f"month={month}" / f"day={day}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(partition_dir / "data.parquet", index=False)


def test_get_daily_returns_rows_sorted_by_trade_date_and_respects_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(ParquetDataReader, "_stock_basic_cache", None, raising=False)

    data_dir = tmp_path / "data"
    _write_partition(
        data_dir,
        "2024",
        "01",
        "01",
        pd.DataFrame(
            [
                {"ts_code": "000002.SZ", "trade_date": "2024-01-01", "close": 11.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-01-01", "close": 10.0},
            ]
        ),
    )
    _write_partition(
        data_dir,
        "2024",
        "01",
        "02",
        pd.DataFrame(
            [
                {"ts_code": "000002.SZ", "trade_date": "2024-01-02", "close": 21.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-01-02", "close": 20.0},
            ]
        ),
    )

    reader = ParquetDataReader(data_dir=str(data_dir))
    frame = reader.get_daily(
        ts_codes=["000002.SZ", "000001.SZ"],
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert frame["trade_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-01",
        "2024-01-01",
        "2024-01-02",
        "2024-01-02",
    ]
    assert set(frame["ts_code"].tolist()) == {"000001.SZ", "000002.SZ"}


def test_get_stock_basic_list_filters_by_industry_area_and_search(tmp_path, monkeypatch):
    monkeypatch.setattr(ParquetDataReader, "_stock_basic_cache", None, raising=False)

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ts_code": "600519.SH",
                "symbol": "600519",
                "name": "贵州茅台",
                "industry": "白酒",
                "area": "贵州",
            },
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "industry": "银行",
                "area": "深圳",
            },
        ]
    ).to_parquet(data_dir / "stock_basic.parquet", index=False)

    reader = ParquetDataReader(data_dir=str(data_dir))
    frame = reader.get_stock_basic_list(industry="白酒", area="贵州", search="茅台")

    assert frame["ts_code"].tolist() == ["600519.SH"]
    assert frame["industry"].tolist() == ["白酒"]
    assert frame["area"].tolist() == ["贵州"]
