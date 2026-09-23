from pathlib import Path

import pandas as pd
import pytest

from app.utils.parquet_writer import save_to_parquet
from app.utils.stock_partition import (
    rebuild_all_tables,
    rebuild_stock_partition,
    resolve_table_name,
    stock_partition_path,
)


def _write_daily(root: Path, table: str, rows: list) -> None:
    frame = pd.DataFrame(rows)
    for trade_date, group in frame.groupby("trade_date"):
        save_to_parquet(group, trade_date, f"{table}/daily", str(root))


def _read_stock(root: Path, table: str, ts_code: str) -> pd.DataFrame:
    return pd.read_parquet(stock_partition_path(str(root), table, ts_code))


def test_full_rebuild_writes_one_file_per_stock_sorted(tmp_path):
    _write_daily(tmp_path, "daily_history", [
        {"ts_code": "000002.SZ", "trade_date": "2026-01-02", "close": 21.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "close": 10.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 11.0},
    ])

    stats = rebuild_stock_partition("daily_history", data_dir=str(tmp_path))

    assert stats["mode"] == "full"
    assert stats["stocks"] == 2
    stock = _read_stock(tmp_path, "daily_history", "000001.SZ")
    assert stock["trade_date"].tolist() == ["2026-01-01", "2026-01-02"]
    assert (stock["ts_code"] == "000001.SZ").all()
    # 日期分区无关代码不混入；换名后无残留 staging/bak
    assert not (tmp_path / "daily_history" / "stock_staging").exists()
    assert not (tmp_path / "daily_history" / "stock_bak").exists()


def test_window_rebuild_merges_into_existing_stock_partition(tmp_path):
    _write_daily(tmp_path, "daily_basic", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "close": 10.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 11.0},
    ])
    rebuild_stock_partition("daily_basic", data_dir=str(tmp_path))

    # 窗口：新交易日 + 既有交易日的修正值（keep last 覆盖）
    _write_daily(tmp_path, "daily_basic", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 99.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 12.0},
    ])
    stats = rebuild_stock_partition(
        "daily_basic", start_date="2026-01-02", end_date="20260103", data_dir=str(tmp_path)
    )

    assert stats["mode"] == "window"
    stock = _read_stock(tmp_path, "daily_basic", "000001.SZ")
    assert stock["trade_date"].tolist() == ["2026-01-01", "2026-01-02", "2026-01-03"]
    by_date = stock.set_index("trade_date")["close"]
    assert by_date["2026-01-01"] == 10.0   # 窗口外不动
    assert by_date["2026-01-02"] == 99.0   # 新值覆盖旧值
    assert by_date["2026-01-03"] == 12.0


def test_adj_factor_alias_resolves_to_stk_factor(tmp_path):
    _write_daily(tmp_path, "stk_factor", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "adj_factor": 12.3},
    ])

    stats = rebuild_stock_partition("adj_factor", data_dir=str(tmp_path))

    assert stats["table"] == "stk_factor"
    assert resolve_table_name("adj_factor") == "stk_factor"
    stock = _read_stock(tmp_path, "stk_factor", "000001.SZ")
    assert stock.iloc[0]["adj_factor"] == 12.3


def test_unknown_table_raises_keyerror():
    with pytest.raises(KeyError):
        resolve_table_name("no_such_table")


def test_full_rebuild_without_daily_partitions_raises(tmp_path):
    with pytest.raises(ValueError):
        rebuild_stock_partition("moneyflow", data_dir=str(tmp_path))


def test_window_rebuild_without_stock_dir_falls_back_to_full(tmp_path):
    _write_daily(tmp_path, "moneyflow", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "close": 10.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 11.0},
        {"ts_code": "000002.SZ", "trade_date": "2026-01-01", "close": 20.0},
        {"ts_code": "000002.SZ", "trade_date": "2026-01-02", "close": 21.0},
    ])

    # 股票分区尚不存在：窗口增量自动转全量，避免只写窗口内几行就通过
    # 新鲜度检查、个股历史查询静默丢历史
    stats = rebuild_stock_partition(
        "moneyflow", start_date="2026-01-02", end_date="2026-01-02", data_dir=str(tmp_path)
    )

    assert stats["mode"] == "full"
    assert len(_read_stock(tmp_path, "moneyflow", "000002.SZ")) == 2


def test_window_rebuild_backfills_new_codes_full_history(tmp_path):
    _write_daily(tmp_path, "daily_history", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "close": 10.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 11.0},
    ])
    rebuild_stock_partition("daily_history", data_dir=str(tmp_path))

    # 新代码进入日期分区（两天历史），但增量窗口只覆盖最新一天
    _write_daily(tmp_path, "daily_history", [
        {"ts_code": "000003.SZ", "trade_date": "2026-01-02", "close": 30.0},
        {"ts_code": "000003.SZ", "trade_date": "2026-01-03", "close": 31.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 12.0},
    ])
    stats = rebuild_stock_partition(
        "daily_history", start_date="20260103", end_date="20260103", data_dir=str(tmp_path)
    )

    assert stats["mode"] == "window"
    # 新代码回填了完整历史而不是只有窗口当天
    assert _read_stock(tmp_path, "daily_history", "000003.SZ")["trade_date"].tolist() == [
        "2026-01-02", "2026-01-03",
    ]
    # 既有代码照常合并窗口
    assert _read_stock(tmp_path, "daily_history", "000001.SZ")["trade_date"].tolist() == [
        "2026-01-01", "2026-01-02", "2026-01-03",
    ]


def test_job_wrapper_honors_window_and_full_refresh_env(tmp_path, monkeypatch):
    import app.utils.stock_partition_rebuild as job

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_daily(tmp_path, "stk_factor", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "close": 10.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-02", "close": 11.0},
    ])
    rebuild_stock_partition("stk_factor", data_dir=str(tmp_path))

    # 窗口环境变量 → 增量合并新交易日，既有历史保留
    _write_daily(tmp_path, "stk_factor", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-03", "close": 12.0},
    ])
    monkeypatch.setenv("DATA_JOB_START_DATE", "2026-01-03")
    monkeypatch.setenv("DATA_JOB_END_DATE", "2026-01-03")
    assert job.main() == 0
    assert len(_read_stock(tmp_path, "stk_factor", "000001.SZ")) == 3

    # FULL_REFRESH → 忽略窗口走全量，仍然成功
    _write_daily(tmp_path, "stk_factor", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-04", "close": 13.0},
    ])
    monkeypatch.setenv("DATA_JOB_FULL_REFRESH", "true")
    assert job.main() == 0
    assert len(_read_stock(tmp_path, "stk_factor", "000001.SZ")) == 4


def test_daily_fetch_job_auto_rebuilds_stock_partition(tmp_path, monkeypatch):
    from app.utils.parquet_job_helpers import DailyFetchJob

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_JOB_TRADE_DATE", "2026-01-05")

    class FakeJob(DailyFetchJob):
        job_name = "fake_daily"
        rel_table = "daily_history/daily"
        rate_limit_seconds = 0

        def fetch_one(self, trade_date):
            return pd.DataFrame([
                {"ts_code": "000001.SZ", "trade_date": trade_date, "close": 42.0},
            ])

    assert FakeJob(api=None).run() == 1

    # 下载落盘后股票分区自动生成，无需单独跑重建作业
    stock = _read_stock(tmp_path, "daily_history", "000001.SZ")
    assert stock["trade_date"].tolist() == ["2026-01-05"]
    assert stock.iloc[0]["close"] == 42.0


def test_auto_rebuild_helper_skips_non_daily_and_kill_switch(tmp_path, monkeypatch):
    from app.utils.stock_partition import auto_rebuild_stock_partition

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # 财务三表等非日频表不在股票分区范围
    assert auto_rebuild_stock_partition("income_statement", ["20260105"]) is None
    # 开关关闭时不做任何事
    monkeypatch.setenv("DATA_JOB_AUTO_REBUILD", "0")
    assert auto_rebuild_stock_partition("daily_history/daily", ["20260105"]) is None


def test_rebuild_all_tables_skips_failed_tables(tmp_path, capsys):
    _write_daily(tmp_path, "cyq_perf", [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-01", "winner_rate": 55.5},
    ])

    results = rebuild_all_tables(data_dir=str(tmp_path))

    assert len(results) == 5
    failed = {r["table"] for r in results if r.get("mode") == "failed"}
    skipped = {r["table"] for r in results if r.get("mode") == "skipped"}
    assert "cyq_perf" not in failed   # 有数据的表成功
    assert "cyq_perf" not in skipped
    assert not failed                 # 空表是跳过而不是失败
    assert skipped                    # 其余空表跳过但被兜住
    assert _read_stock(tmp_path, "cyq_perf", "000001.SZ").iloc[0]["winner_rate"] == 55.5
