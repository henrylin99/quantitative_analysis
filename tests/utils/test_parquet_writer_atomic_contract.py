"""数据分区原子写合约：覆盖写后必须能读到新数据，且不留 .tmp 半截文件。"""
from pathlib import Path

import pandas as pd

from app.utils.parquet_writer import save_single_parquet, save_to_parquet


def test_save_to_parquet_overwrite_keeps_single_complete_file(tmp_path):
    """重复写同一天是覆盖语义：rename 原子替换，读方只看到完整新文件。"""
    path = Path(tmp_path) / "t" / "year=2024" / "month=06" / "day=04" / "data.parquet"

    save_to_parquet(
        pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "2024-06-04", "close": 10.0}]),
        "2024-06-04",
        "t",
        str(tmp_path),
    )
    save_to_parquet(
        pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "2024-06-04", "close": 12.0}]),
        "2024-06-04",
        "t",
        str(tmp_path),
    )

    frame = pd.read_parquet(path)
    assert frame["close"].tolist() == [12.0]
    assert not list(path.parent.glob("*.tmp.*")), "原子写不允许留下临时文件"


def test_save_single_parquet_roundtrip(tmp_path):
    frame = pd.DataFrame([{"ts_code": "000001.SZ", "industry": "银行"}])

    written = save_single_parquet(frame, "stock_basic.parquet", str(tmp_path))

    assert written == 1
    out = pd.read_parquet(Path(tmp_path) / "stock_basic.parquet")
    assert out["industry"].tolist() == ["银行"]
    assert not list((Path(tmp_path)).glob("*.tmp.*"))
