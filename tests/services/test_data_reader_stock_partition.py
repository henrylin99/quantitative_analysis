"""股票分区读取路径的合约测试。

用「股票分区里写与日期分区不同的 close 值」来判定结果走了哪条路径：
读到 999 说明命中股票分区，读到日期分区的值说明发生了回退。
"""

import pandas as pd

from app.services.data_reader import ParquetDataReader
from app.utils.parquet_writer import save_to_parquet
from app.utils.stock_partition import rebuild_stock_partition


TABLE = "daily_history"


def _write_daily(data_dir, rows):
    frame = pd.DataFrame(rows)
    for trade_date, group in frame.groupby("trade_date"):
        save_to_parquet(group, trade_date, f"{TABLE}/daily", str(data_dir))


def _write_stock_partition(data_dir, ts_code, rows):
    path = data_dir / TABLE / "stock" / f"ts_code={ts_code}" / "data.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


DAILY_ROWS = [
    {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 11.0},
    {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 12.0},
    {"ts_code": "000002.SZ", "trade_date": "2026-01-02", "close": 21.0},
    {"ts_code": "000002.SZ", "trade_date": "2026-01-03", "close": 22.0},
    {"ts_code": "399001.SZ", "trade_date": "2026-01-03", "close": 9999.0},
]


def test_fresh_stock_partition_is_preferred(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 999.0},
    ])

    reader = ParquetDataReader(data_dir=str(tmp_path))
    frame = reader.get_daily(ts_codes=["000001.SZ"])

    # 999 = 来自股票分区而非日期分区；无关代码与指数不混入
    assert set(frame["close"]) == {999.0}
    assert set(frame["ts_code"]) == {"000001.SZ"}


def test_stale_stock_partition_falls_back_to_daily_tree(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    # 股票分区缺少最新交易日 2026-01-03 → 判过期 → 整体走日期分区
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
    ])

    reader = ParquetDataReader(data_dir=str(tmp_path))
    frame = reader.get_daily(ts_codes=["000001.SZ"])

    assert frame["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-02", "2026-01-03"]
    assert set(frame["close"]) == {11.0, 12.0}


def test_end_date_beyond_latest_partition_still_uses_stock(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 999.0},
    ])

    reader = ParquetDataReader(data_dir=str(tmp_path))
    # end_date 传到分区之后的日子（如非交易日的今天）：只要求覆盖到最新分区即可
    frame = reader.get_daily(ts_codes=["000001.SZ"], end_date="2026-01-31")

    assert set(frame["close"]) == {999.0}
    # 历史窗口边界仍然生效
    frame = reader.get_daily(ts_codes=["000001.SZ"], end_date="2026-01-02")
    assert frame["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-02"]


def test_missing_code_falls_back_while_fresh_code_uses_stock(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 999.0},
    ])

    reader = ParquetDataReader(data_dir=str(tmp_path))
    frame = reader.get_daily(ts_codes=["000001.SZ", "000002.SZ"])

    got = frame.groupby("ts_code")["close"].apply(set).to_dict()
    assert got["000001.SZ"] == {999.0}          # 命中股票分区
    assert got["000002.SZ"] == {21.0, 22.0}     # 无分区 → 日期分区兜底


def test_rebuilt_partitions_return_same_result_as_daily_tree(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    reader = ParquetDataReader(data_dir=str(tmp_path))
    baseline = reader.get_daily(
        ts_codes=["000001.SZ", "000002.SZ"], start_date="2026-01-02", end_date="2026-01-03"
    )

    rebuild_stock_partition(TABLE, data_dir=str(tmp_path))
    frame = ParquetDataReader(data_dir=str(tmp_path)).get_daily(
        ts_codes=["000001.SZ", "000002.SZ"], start_date="2026-01-02", end_date="2026-01-03"
    )

    pd.testing.assert_frame_equal(
        frame.reset_index(drop=True), baseline.reset_index(drop=True)
    )


def test_kill_switch_env_disables_stock_partition_read(tmp_path, monkeypatch):
    _write_daily(tmp_path, DAILY_ROWS)
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
    ])
    monkeypatch.setenv("STOCK_PARTITION_READ", "0")

    reader = ParquetDataReader(data_dir=str(tmp_path))
    frame = reader.get_daily(ts_codes=["000001.SZ"])

    assert set(frame["close"]) == {11.0, 12.0}


def test_get_latest_daily_prefers_stock_partition_file(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 999.0},
    ])

    reader = ParquetDataReader(data_dir=str(tmp_path))
    row = reader.get_latest_daily("000001.SZ")

    assert float(row["close"]) == 999.0  # 999 = 来自个股分区文件
    assert reader.get_latest_close("000001.SZ") == 999.0


def test_get_latest_daily_falls_back_when_stock_partition_stale(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)
    # 个股分区缺少最新交易日 → 回退全市场最新日期分区
    _write_stock_partition(tmp_path, "000001.SZ", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 999.0},
    ])

    reader = ParquetDataReader(data_dir=str(tmp_path))

    assert float(reader.get_latest_daily("000001.SZ")["close"]) == 12.0


def test_get_latest_daily_falls_back_without_stock_partition(tmp_path):
    _write_daily(tmp_path, DAILY_ROWS)

    reader = ParquetDataReader(data_dir=str(tmp_path))

    # 无个股分区文件的代码读最新日期分区；全市场都不存在的代码返回 None
    assert float(reader.get_latest_daily("000002.SZ")["close"]) == 22.0
    assert reader.get_latest_daily("000009.SH") is None
    assert reader.get_latest_close("000009.SH") is None


def test_tables_without_stock_partitions_keep_old_path(tmp_path):
    # 季度财报表无 /daily 目录，不应尝试股票分区
    frame_in = pd.DataFrame([
        {"ts_code": "000001.SZ", "end_date": "2026-06-30", "n_income": 100.0},
    ])
    base = tmp_path / "income_statement" / "year=2026" / "month=06" / "day=30"
    base.mkdir(parents=True)
    frame_in.to_parquet(base / "data.parquet", index=False)

    reader = ParquetDataReader(data_dir=str(tmp_path))
    frame = reader.get_income_statement(["000001.SZ"])

    assert frame.iloc[0]["n_income"] == 100.0
