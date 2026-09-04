"""Parquet 状态存储并发与损坏保护的回归测试。

覆盖 2026-08 修复的问题:
- 原子写（临时文件 + rename）：读方不会观察到写了一半的文件
- 读损坏文件抛 StateStoreError 而不是返回空表（返回空表会让后续
  read-modify-write 把整表静默清空）
- 文件锁保证并发的 create_run 不丢数据、不产生重复 id
"""
import concurrent.futures
import os

import pandas as pd
import pytest

from app.services.data_jobs.parquet_state_store import ParquetDataJobStateStore
from app.services.parquet_state_store import ParquetStateStore, StateStoreError


def test_write_frame_is_atomic_and_readable(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path))
    df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
    store.write_frame("t", df)
    # 原子写后不留临时文件
    leftovers = [p for p in os.listdir(tmp_path) if ".tmp." in p]
    assert not leftovers
    assert store.read_frame("t").equals(df)


def test_corrupted_file_raises_instead_of_returning_empty(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path))
    store.write_frame("t", pd.DataFrame({"a": [1]}))
    with open(store.path_for("t"), "wb") as f:
        f.write(b"not a parquet file")
    with pytest.raises(StateStoreError):
        store.read_frame("t")


def test_missing_file_returns_empty_frame(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path))
    assert store.read_frame("nonexistent").empty


def test_concurrent_create_runs_do_not_lose_rows(tmp_path):
    """多线程并发 create_run：文件锁 + 原子写应保证零丢失、零重复 id。"""
    base_dir = str(tmp_path / "data_job_state")

    def create(i):
        return ParquetDataJobStateStore(base_dir=base_dir).create_run(
            job_type="concurrent_test", params={"i": i}
        ).id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(create, range(40)))

    runs = ParquetDataJobStateStore(base_dir=base_dir).list_runs(limit=10000)
    assert len(runs) == 40, "并发写入不能丢行"
    assert len(set(ids)) == 40, "并发分配的 id 不能重复"


def test_writer_and_reader_never_see_partial_file(tmp_path):
    """持续读的同时持续写，读方永远读到完整可解析的表。"""
    store = ParquetStateStore(base_dir=str(tmp_path))
    store.write_frame("t", pd.DataFrame({"a": [1]}))

    def write_many():
        for i in range(30):
            store.write_frame("t", pd.DataFrame({"a": [i]}))

    def read_many():
        for _ in range(60):
            df = store.read_frame("t")  # 损坏/半写会抛 StateStoreError
            assert not df.empty

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        w = pool.submit(write_many)
        r = pool.submit(read_many)
        w.result()
        r.result()
