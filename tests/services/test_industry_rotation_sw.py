"""行业轮动 × 申万指数交叉验证：成分重叠映射与秩相关的单元测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.industry_rotation_service import (
    _map_industry_to_sw,
    _sw_l1_context,
)


class _Reader:
    """最小 reader 桩：返回固定指数日线（25 日，满足 21 日动量窗口）与成分表。"""

    def __init__(self):
        dates = pd.bdate_range("2025-11-20", periods=25).strftime("%Y%m%d")
        frames = []
        for code, base in (("801010.SI", 1000.0), ("801030.SI", 2000.0)):
            frames.append(pd.DataFrame({
                "ts_code": code,
                "trade_date": dates,
                "close": [base + i * (5.0 if code == "801010.SI" else -2.0)
                          for i in range(25)],
            }))
        self.index_daily_df = pd.concat(frames, ignore_index=True)
        self.members_df = pd.DataFrame({
            "index_code": ["801010.SI"] * 3 + ["801030.SI"] * 2,
            "con_code": ["000001.SZ", "000002.SZ", "000003.SZ",
                         "600000.SH", "600001.SH"],
            "out_date": [None] * 5,
        })

    def get_index_daily(self, codes, start, end):
        return self.index_daily_df[self.index_daily_df["ts_code"].isin(codes)]

    def get_index_members(self, active_only=True):
        if active_only:
            return self.members_df[self.members_df["out_date"].isna()]
        return self.members_df


def test_sw_l1_context_momentum_and_members():
    mom, members = _sw_l1_context(_Reader(), pd.Timestamp("2026-01-05"))
    assert set(mom) == {"801010.SI", "801030.SI"}
    # 20 日动量 = 末值 / 21 个交易日前值 - 1
    c = _Reader().index_daily_df
    c010 = c[c["ts_code"] == "801010.SI"]["close"].reset_index(drop=True)
    assert mom["801010.SI"] == pytest.approx(c010.iloc[-1] / c010.iloc[-21] - 1)
    assert members["801010.SI"] == {"000001.SZ", "000002.SZ", "000003.SZ"}


def test_sw_l1_context_short_history_returns_none():
    reader = _Reader()
    reader.index_daily_df = reader.index_daily_df.head(2)
    mom, _ = _sw_l1_context(reader, pd.Timestamp("2026-01-05"))
    assert mom is None


def test_map_industry_to_sw_overlap():
    members = {"801010.SI": {f"00000{i}.SZ" for i in range(1, 7)},
               "801030.SI": {"600000.SH"}}
    # 6 只成分全部落在 801010（覆盖 100%，超过最小重叠 5）→ 命中
    stocks = {f"00000{i}.SZ" for i in range(1, 7)}
    assert _map_industry_to_sw(stocks, members) == "801010.SI"
    # 仅 1 只重叠且低于 30% 覆盖 → 不映射
    assert _map_industry_to_sw({"600000.SH", "300001.SZ", "300002.SZ",
                                "300003.SZ", "300004.SZ"}, members) is None
