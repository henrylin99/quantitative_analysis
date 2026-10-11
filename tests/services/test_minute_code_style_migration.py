"""分钟数据代码风格统一（3.1）：normalize/aliases、写侧归一、存量迁移脚本。"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.services.minute_code_style import (
    is_tushare_style,
    minute_code_aliases,
    normalize_minute_code,
)
from app.services.minute_parquet_reader import MinuteParquetReader
from app.services.minute_parquet_store import MinuteParquetStore


@pytest.mark.module_data_jobs
class TestNormalizeMinuteCode:
    def test_bs_style_to_tushare(self):
        assert normalize_minute_code("sz.000001") == "000001.SZ"
        assert normalize_minute_code("sh.600000") == "600000.SH"
        assert normalize_minute_code("bj.832000") == "832000.BJ"

    def test_tushare_style_passthrough_and_case(self):
        assert normalize_minute_code("000001.SZ") == "000001.SZ"
        assert normalize_minute_code("600000.sh") == "600000.SH"

    def test_bare_digits_infer_market(self):
        assert normalize_minute_code("600000") == "600000.SH"
        assert normalize_minute_code("300502") == "300502.SZ"
        assert normalize_minute_code("832000") == "832000.BJ"
        assert normalize_minute_code("430047") == "430047.BJ"
        assert normalize_minute_code("920002") == "920002.BJ"

    def test_unknown_style_returned_as_is(self):
        assert normalize_minute_code("AAPL") == "AAPL"
        assert normalize_minute_code("") == ""


@pytest.mark.module_data_jobs
class TestMinuteCodeAliases:
    def test_canonical_query_matches_legacy_storage(self):
        aliases = minute_code_aliases("000001.SZ")
        assert "000001.SZ" in aliases
        assert "sz.000001" in aliases

    def test_legacy_query_matches_canonical_storage(self):
        aliases = minute_code_aliases("sh.600000")
        assert "600000.SH" in aliases
        assert "sh.600000" in aliases

    def test_bare_digits_cover_all_markets(self):
        aliases = minute_code_aliases("300502")
        assert {"300502.SZ", "300502.SH", "300502.BJ"} <= aliases

    def test_is_tushare_style(self):
        assert is_tushare_style("000001.SZ") is True
        assert is_tushare_style("sz.000001") is False
        assert is_tushare_style("000001") is False


@pytest.mark.module_data_jobs
class TestStoreNormalizesOnWrite:
    def test_write_frame_stores_tushare_style(self, tmp_path):
        frame = pd.DataFrame(
            [
                {"ts_code": "sz.000001", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 10.1},
                {"ts_code": "sh.600000", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 8.1},
            ]
        )
        store = MinuteParquetStore(data_dir=str(tmp_path))
        store.write_frame(frame, "5min")

        stored = pd.read_parquet(tmp_path / "stock_minute" / "5min" / "year=2026" / "month=10" / "day=09" / "data.parquet")
        assert set(stored["ts_code"]) == {"000001.SZ", "600000.SH"}

    def test_mixed_style_same_bar_deduped_after_normalization(self, tmp_path):
        # 同一根 bar 以两种风格先后写入：归一后应去重 keep=last
        day_dir = tmp_path / "stock_minute" / "5min" / "year=2026" / "month=10" / "day=09"
        day_dir.mkdir(parents=True)
        pd.DataFrame(
            [{"ts_code": "sz.000001", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 10.0}]
        ).to_parquet(day_dir / "data.parquet", index=False)

        frame = pd.DataFrame(
            [{"ts_code": "000001.SZ", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 10.5}]
        )
        MinuteParquetStore(data_dir=str(tmp_path)).write_frame(frame, "5min")

        stored = pd.read_parquet(day_dir / "data.parquet")
        assert len(stored) == 1
        assert stored.iloc[0]["close"] == 10.5


@pytest.mark.module_data_jobs
class TestReaderTransitionCompat:
    def test_old_style_query_matches_new_style_storage(self, tmp_path):
        # 迁移后的存量：存储为规范风格，查询仍可用旧风格
        day_dir = tmp_path / "stock_minute" / "5min" / "year=2026" / "month=10" / "day=09"
        day_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {"ts_code": "600000.SH", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 8.1},
                {"ts_code": "600000.SH", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 40), "close": 8.2},
            ]
        ).to_parquet(day_dir / "data.parquet", index=False)

        data = MinuteParquetReader(data_dir=str(tmp_path)).get_data(ts_code="sh.600000", period_type="5min")
        assert len(data) == 2


def _write_legacy_partition(data_dir: Path, rows: list[dict]) -> Path:
    day_dir = data_dir / "stock_minute" / "5min" / "year=2026" / "month=10" / "day=09"
    day_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(day_dir / "data.parquet", index=False)
    return day_dir / "data.parquet"


@pytest.mark.module_data_jobs
class TestMigrationScript:
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "scripts/migrate_minute_codes.py", "--data-dir", *args],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )

    def test_dry_run_reports_without_writing(self, tmp_path):
        path = _write_legacy_partition(
            tmp_path,
            [{"ts_code": "sz.000001", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 10.0}],
        )
        before = pd.read_parquet(path)

        result = self._run(str(tmp_path))

        assert result.returncode == 0
        assert "dry-run" in result.stdout or "dry-run" in result.stderr
        after = pd.read_parquet(path)
        assert list(after["ts_code"]) == list(before["ts_code"])

    def test_execute_rewrites_and_dedupes_dual_style(self, tmp_path):
        path = _write_legacy_partition(
            tmp_path,
            [
                {"ts_code": "sz.000001", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 10.0},
                # 同一根 bar 已有一份规范风格（如手工补数）：迁移后应合并
                {"ts_code": "000001.SZ", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 10.8},
                {"ts_code": "000001.SZ", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 40), "close": 10.2},
            ],
        )

        result = self._run(str(tmp_path), "--execute")

        assert result.returncode == 0
        migrated = pd.read_parquet(path)
        assert set(migrated["ts_code"]) == {"000001.SZ"}
        assert len(migrated) == 2  # 双风格同 bar 合并 + 保留另一根
        assert migrated[migrated["datetime"] == datetime(2026, 10, 9, 9, 35)].iloc[0]["close"] == 10.8

    def test_execute_is_idempotent(self, tmp_path):
        path = _write_legacy_partition(
            tmp_path,
            [{"ts_code": "sh.600000", "period_type": "5min", "datetime": datetime(2026, 10, 9, 9, 35), "close": 8.0}],
        )
        assert self._run(str(tmp_path), "--execute").returncode == 0
        first = pd.read_parquet(path)

        result = self._run(str(tmp_path), "--execute")
        assert result.returncode == 0
        assert pd.read_parquet(path).equals(first)
