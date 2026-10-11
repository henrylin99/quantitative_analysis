"""index_daily 作业单元测试：upsert 合并、申万列映射、清单解析。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

UTILS_DIR = Path(__file__).resolve().parents[2] / "app" / "utils"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from index_daily import (  # noqa: E402
    _SCHEMA,
    _SW_L1_CODES,
    _fetch_sw,
    _upsert_flat_table,
    _upsert_index,
    resolve_index_codes,
)


# ------------------------------------------------------------------
# resolve_index_codes
# ------------------------------------------------------------------

def test_resolve_codes_contains_benchmark_and_sw_l1(monkeypatch):
    monkeypatch.delenv("DATA_JOB_INDEX_CODES", raising=False)
    codes = resolve_index_codes()
    assert "000300.SH" in codes            # 回测默认基准（此前缺失）
    assert "000001.SH" in codes
    assert f"{_SW_L1_CODES[0]}.SI" in codes
    assert len(codes) == 9 + len(_SW_L1_CODES)


def test_resolve_codes_env_override(monkeypatch):
    monkeypatch.setenv("DATA_JOB_INDEX_CODES", "000300.SH, 801010.SI")
    assert resolve_index_codes() == ["000300.SH", "801010.SI"]


# ------------------------------------------------------------------
# sw 列映射（fake akshare）
# ------------------------------------------------------------------

def _fake_akshare_frame():
    return pd.DataFrame({
        "代码": ["801010"] * 4,
        "日期": ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"],
        "开盘": [10.0, 10.5, 11.0, 10.8],
        "收盘": [10.5, 11.0, 10.8, 11.2],
        "最高": [10.6, 11.1, 11.2, 11.3],
        "最低": [9.9, 10.4, 10.7, 10.7],
        "成交量": [100.0, 110.0, 90.0, 120.0],
        "成交额": [1.0, 1.1, 0.9, 1.2],
    })


def test_fetch_sw_maps_columns_and_computes_pre_close(monkeypatch):
    import types

    fake_mod = types.ModuleType("akshare")
    fake_mod.index_hist_sw = lambda symbol, period: _fake_akshare_frame()
    monkeypatch.setitem(sys.modules, "akshare", fake_mod)

    df = _fetch_sw("801010.SI", "20260101", "20261231")
    assert list(df.columns) == _SCHEMA
    assert (df["ts_code"] == "801010.SI").all()
    assert df["trade_date"].iloc[0] == "20261006"
    # 首行 pre_close 为空，之后 close.shift(1)
    assert pd.isna(df["pre_close"].iloc[0])
    assert df["pre_close"].iloc[1] == 10.5
    # pct_chg 百分比口径：11.0/10.5 - 1
    assert df["pct_chg"].iloc[1] == pytest.approx(11.0 / 10.5 * 100 - 100)


def test_fetch_sw_window_filter(monkeypatch):
    import types

    fake_mod = types.ModuleType("akshare")
    fake_mod.index_hist_sw = lambda symbol, period: _fake_akshare_frame()
    monkeypatch.setitem(sys.modules, "akshare", fake_mod)

    df = _fetch_sw("801010.SI", "20261007", "20261008")
    assert df["trade_date"].tolist() == ["20261007", "20261008"]


# ------------------------------------------------------------------
# upsert 合并（tmp 数据目录）
# ------------------------------------------------------------------

def test_upsert_index_merges_and_dedups(tmp_path):
    frame1 = pd.DataFrame({
        "ts_code": ["000300.SH"] * 2,
        "trade_date": ["20260101", "20260102"],
        "close": [4000.0, 4010.0],
    })
    frame2 = pd.DataFrame({
        "ts_code": ["000300.SH"] * 2,
        "trade_date": ["20260102", "20260105"],  # 0102 重拉（修订值），0105 新增
        "close": [4012.0, 4030.0],
    })
    assert _upsert_index("000300.SH", frame1, data_dir=str(tmp_path)) == 2
    total = _upsert_index("000300.SH", frame2, data_dir=str(tmp_path))
    assert total == 3  # 同日 keep=last → 修订值覆盖

    saved = pd.read_parquet(
        tmp_path / "index_daily" / "stock" / "ts_code=000300.SH" / "data.parquet")
    assert sorted(saved["trade_date"]) == ["20260101", "20260102", "20260105"]
    assert saved.loc[saved["trade_date"] == "20260102", "close"].iloc[0] == 4012.0


def test_upsert_flat_table_dedups_on_keys(tmp_path):
    frame = pd.DataFrame({
        "index_code": ["801010.SI", "801010.SI"],
        "con_code": ["000001.SZ", "000001.SZ"],
        "in_date": ["20211213", "20211213"],
        "out_date": [None, "20230101"],
    })
    _upsert_flat_table(frame, "test_members.parquet", str(tmp_path),
                       key_cols=["index_code", "con_code", "in_date"])
    total = _upsert_flat_table(frame, "test_members.parquet", str(tmp_path),
                               key_cols=["index_code", "con_code", "in_date"])
    saved = pd.read_parquet(tmp_path / "test_members.parquet")
    assert total == 1  # 复跑幂等：同键去重
    assert len(saved) == 1
