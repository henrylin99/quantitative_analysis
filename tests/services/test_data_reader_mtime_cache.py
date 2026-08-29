"""单文件表 mtime 缓存合约：文件被任务重写后，任何进程下次读取必须拿到新数据。"""
import os

import pandas as pd
import pytest

from app.services.data_reader import ParquetDataReader


@pytest.fixture(autouse=True)
def _clear_cache():
    ParquetDataReader._single_file_cache.clear()
    yield
    ParquetDataReader._single_file_cache.clear()


def _write(path, rows):
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_cache_refreshes_when_file_is_rewritten(tmp_path):
    path = tmp_path / "stock_basic.parquet"
    _write(path, [{"ts_code": "000001.SZ", "name": "旧名称"}])

    reader = ParquetDataReader(data_dir=str(tmp_path))
    assert reader.get_stock_basic()["name"].iloc[0] == "旧名称"

    # 模拟另一个进程（Celery worker）重写文件；强制不同 mtime 避免时钟分辨率问题
    _write(path, [{"ts_code": "000001.SZ", "name": "新名称"}])
    stat = path.stat()
    os.utime(path, (stat.st_atime + 10, stat.st_mtime + 10))

    frame = reader.get_stock_basic()

    assert frame["name"].iloc[0] == "新名称"


def test_same_filename_in_different_data_dirs_do_not_share_cache(tmp_path):
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _write(dir_a / "stock_business.parquet", [{"ts_code": "000001.SZ", "pe": 1.0}])
    _write(dir_b / "stock_business.parquet", [{"ts_code": "000001.SZ", "pe": 2.0}])

    reader_a = ParquetDataReader(data_dir=str(dir_a))
    reader_b = ParquetDataReader(data_dir=str(dir_b))

    assert reader_a.get_stock_business()["pe"].iloc[0] == 1.0
    assert reader_b.get_stock_business()["pe"].iloc[0] == 2.0


def test_invalid_entry_still_available_for_compat(tmp_path):
    """invalidate_stock_business_cache 兼容入口仍可显式清缓存。"""
    path = tmp_path / "stock_business.parquet"
    _write(path, [{"ts_code": "000001.SZ", "pe": 1.0}])
    reader = ParquetDataReader(data_dir=str(tmp_path))
    reader.get_stock_business()

    ParquetDataReader.invalidate_stock_business_cache()

    assert ParquetDataReader._single_file_cache == {}
