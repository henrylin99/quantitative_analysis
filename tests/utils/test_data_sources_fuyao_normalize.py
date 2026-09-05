"""归一化层合约测试：单位换算、时区解析、字段映射、schema 同构。"""

import numpy as np
import pandas as pd
import pytest

from app.utils.data_sources.fuyao_normalize import (
    DAILY_COLUMNS,
    daily_frame_from_dump,
    daily_frame_from_kline_rows,
    financial_items_to_frame,
    snapshot_rows_to_quote_frame,
    snapshot_rows_to_stock_basic,
)


def _beijing_midnight_ms(ymd: str) -> int:
    from datetime import datetime

    dt = datetime.strptime(ymd, "%Y%m%d")
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() * 1000) - 8 * 3600 * 1000


def _dump_row(ts_code, ymd, o, h, l, c, volume, turnover, adjusted="none"):
    return {
        "thscode": ts_code, "currency": "CNY", "interval": "1d", "adjusted": adjusted,
        "date_ms": _beijing_midnight_ms(ymd),
        "open_price": o, "high_price": h, "low_price": l, "close_price": c,
        "volume": volume, "turnover": turnover,
    }


def _dump_frame(rows):
    return pd.DataFrame(rows)


# ---- daily：dump → tushare 口径 ----

def test_daily_units_and_pre_close_derivation():
    rows = [
        _dump_row("000001.SZ", "20260601", 10.0, 11.0, 9.9, 10.5, 1_000_000, 105_000_000),
        _dump_row("000001.SZ", "20260602", 10.5, 11.5, 10.4, 11.0, 1_234_567, 130_000_000),
        _dump_row("600000.SH", "20260601", 9.0, 9.5, 8.9, 9.2, 2_000_000, 180_000_000),
    ]
    df = daily_frame_from_dump(_dump_frame(rows), ["20260601", "20260602"])

    assert list(df.columns) == DAILY_COLUMNS
    # vol: 股 → 手（向下取整）
    row = df[(df.ts_code == "000001.SZ") & (df.trade_date == "20260602")].iloc[0]
    assert row["vol"] == np.floor(1_234_567 / 100)
    # amount: 元 → 千元
    assert row["amount"] == pytest.approx(130_000.0)
    # pre_close 来自前一交易日 close
    assert row["pre_close"] == pytest.approx(10.5)
    assert row["change"] == pytest.approx(0.5)
    assert row["pct_chg"] == pytest.approx(round((11.0 / 10.5 - 1) * 100, 4))
    # 首个交易日无前收盘 → change/pct_chg 为 NaN
    first = df[(df.ts_code == "000001.SZ") & (df.trade_date == "20260601")].iloc[0]
    assert np.isnan(first["pre_close"]) and np.isnan(first["pct_chg"])


def test_daily_single_date_keeps_pre_close_from_dump_context():
    """只取一天时 pre_close 仍由 dump 内前一交易日推导（先推导后过滤）。"""
    rows = [
        _dump_row("000001.SZ", "20260601", 10.0, 11.0, 9.9, 10.5, 1_000_000, 105_000_000),
        _dump_row("000001.SZ", "20260602", 10.5, 11.5, 10.4, 11.0, 1_200_000, 130_000_000),
    ]
    df = daily_frame_from_dump(_dump_frame(rows), ["20260602"])
    assert len(df) == 1
    assert df.iloc[0]["pre_close"] == pytest.approx(10.5)


def test_daily_filters_date_range_and_non_raw_adjusted():
    rows = [
        _dump_row("000001.SZ", "20260601", 10.0, 11.0, 9.9, 10.5, 1_000_000, 105_000_000),
        _dump_row("000001.SZ", "20260603", 10.5, 11.5, 10.4, 11.0, 1_200_000, 130_000_000),
        # 复权口径行必须被拒绝（防御 dump 混源）
        _dump_row("000001.SZ", "20260604", 11.0, 12.0, 10.9, 11.5, 1_200_000, 130_000_000, adjusted="forward"),
    ]
    df = daily_frame_from_dump(_dump_frame(rows), ["20260603", "20260604"])
    assert sorted(df["trade_date"].unique()) == ["20260603"]
    assert len(df) == 1


def test_daily_drops_halted_rows():
    rows = [
        _dump_row("000001.SZ", "20260601", 10.0, 11.0, 9.9, 10.5, 1_000_000, 105_000_000),
        _dump_row("000001.SZ", "20260602", None, None, None, None, 0, 0),  # 停牌日
    ]
    df = daily_frame_from_dump(_dump_frame(rows), ["20260601", "20260602"])
    assert "20260602" not in set(df["trade_date"])


def test_daily_from_kline_rows_maps_metadata():
    rows = [
        {"date_ms": _beijing_midnight_ms("20260601"), "open_price": 1, "high_price": 2,
         "low_price": 0.5, "close_price": 1.5, "volume": 500, "turnover": 750},
        {"date_ms": _beijing_midnight_ms("20260602"), "open_price": 1.5, "high_price": 2.5,
         "low_price": 1.4, "close_price": 2.0, "volume": 600, "turnover": 1200},
    ]
    df = daily_frame_from_kline_rows(rows, "600000.SH")
    assert list(df.columns) == DAILY_COLUMNS
    assert set(df["ts_code"]) == {"600000.SH"}
    assert df.iloc[1]["pre_close"] == pytest.approx(1.5)
    assert df.iloc[0]["vol"] == 5.0


# ---- 财务三表 ----

def test_financial_items_map_to_tushare_columns_with_passthrough():
    items = [{
        "thscode": "600000.SH", "period": "quarterly", "fiscal_year": 2026, "fiscal_period": "Q2",
        "report_date_ms": _beijing_midnight_ms("20260824"), "period_end_ms": _beijing_midnight_ms("20260630"),
        "currency": "CNY", "operating_income": 100, "net_profit": 10, "parent_holder_net_profit": 8,
        "basic_eps": 0.5, "extra_fuyao_field": 42,
    }]
    df = financial_items_to_frame(items, "income", "600000.SH")

    assert df.iloc[0]["ts_code"] == "600000.SH"
    assert df.iloc[0]["end_date"] == "20260630"
    assert df.iloc[0]["ann_date"] == "20260824"
    assert df.iloc[0]["revenue"] == 100        # operating_income → revenue
    assert df.iloc[0]["n_income"] == 10        # net_profit → n_income
    assert df.iloc[0]["n_income_attr_p"] == 8  # parent_holder_net_profit → n_income_attr_p
    assert df.iloc[0]["extra_fuyao_field"] == 42  # 独有字段原名透传
    assert "operating_income" not in df.columns


def test_financial_null_stays_nan_not_zero():
    items = [{
        "thscode": "600000.SH", "report_date_ms": None, "period_end_ms": _beijing_midnight_ms("20260630"),
        "operating_income": 100, "operating_costs": None,
    }]
    df = financial_items_to_frame(items, "income", "600000.SH")
    assert pd.isna(df.iloc[0]["oper_cost"])


def test_financial_unknown_table_raises():
    with pytest.raises(ValueError):
        financial_items_to_frame([], "shares", "600000.SH")


# ---- 快照 ----

def test_quote_frame_handles_dual_field_naming():
    rows = [
        {"thscode": "000001.SZ", "name": "平安银行", "last_price": 11.89, "open_price": 11.86,
         "high_price": 12.0, "low_price": 11.85, "prev_price": 11.88,
         "price_change": 0.01, "price_change_ratio_pct": 0.084, "volume": 100, "turnover": 200},
        {"thscode": "600000.SH", "name": "浦发银行", "last_price": 9.2, "open_price": 9.1,
         "highest_price": 9.4, "lowest_price": 9.0, "prev_close_price": 9.1,
         "price_change": 0.1, "price_change_ratio_pct": 1.1, "volume": None, "turnover": None},
    ]
    df = snapshot_rows_to_quote_frame(rows)
    assert df.iloc[0]["high"] == 12.0 and df.iloc[0]["prev_close"] == 11.88
    assert df.iloc[1]["high"] == 9.4 and df.iloc[1]["prev_close"] == 9.1
    assert np.isnan(df.iloc[1]["volume"])


def test_quote_frame_drops_rows_without_code():
    df = snapshot_rows_to_quote_frame([{"name": "no code"}, {"thscode": "000001.SZ", "last_price": 1}])
    assert len(df) == 1


def test_stock_basic_refresh_names_and_appends_new_codes():
    existing = pd.DataFrame([
        {"ts_code": "000001.SZ", "symbol": "000001", "name": "旧名称", "industry": "银行", "list_status": "L"},
        {"ts_code": "000002.SZ", "symbol": "000002", "name": "万科A", "industry": "地产", "list_status": "L"},
    ])
    rows = [
        {"thscode": "000001.SZ", "name": "平安银行"},
        {"thscode": "300001.SZ", "name": "特锐德"},  # 新增代码
    ]
    df = snapshot_rows_to_stock_basic(rows, existing)
    by_code = df.set_index("ts_code")
    assert by_code.loc["000001.SZ", "name"] == "平安银行"
    assert by_code.loc["000001.SZ", "industry"] == "银行"  # 元数据保留
    assert by_code.loc["000002.SZ", "name"] == "万科A"     # 缺席快照的记录保留
    assert by_code.loc["300001.SZ", "list_status"] == "L"  # 新增记录标记在市
    assert pd.isna(by_code.loc["300001.SZ", "industry"])


def test_stock_basic_from_empty_existing():
    df = snapshot_rows_to_stock_basic([{"thscode": "000001.SZ", "name": "平安银行"}], None)
    assert df.iloc[0]["symbol"] == "000001"
    assert df.iloc[0]["list_status"] == "L"
