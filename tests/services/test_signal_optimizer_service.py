"""信号参数寻优测试：筹码阈值 walk-forward、轮动权重、写回单一源一致性。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.signal_defs import (
    SignalThresholds,
    clear_threshold_override,
    current_thresholds,
    merge_thresholds,
    save_threshold_override,
)
from app.services.signal_optimizer_service import SignalOptimizerService


class _StubReader:
    """构造一个可判定的面板：000001.SZ 恒满足 squeeze，其余不满足。"""

    def __init__(self, n_days: int = 160):
        dates = pd.date_range("2026-01-01", periods=n_days, freq="B")
        codes = [f"60000{i}.SH" for i in range(1, 6)]
        self.dates = dates
        # 筹码：000001 获利盘 65%、筹码区间宽 0.05；其余获利盘 10%、区间宽 0.5
        cyq, daily, flow = [], [], []
        for i, d in enumerate(dates):
            for j, c in enumerate(codes):
                # 000001 恒涨（其余横盘）→ 信号股超额恒正；
                # 获利盘锯齿抬升（resonance 要求 winner_chg>0，且不越过 70 上限）
                price = (10.0 + i * 0.05) if j == 0 else 10.0
                hi = (60.0 + (i % 10) * 0.1) if j == 0 else 10.0
                cyq.append({"ts_code": c, "trade_date": d, "winner_rate": hi,
                            "cost_5pct": 9.0 if j == 0 else 5.0,
                            "cost_50pct": 10.0, "cost_95pct": 9.5 if j == 0 else 15.0})
                daily.append({"ts_code": c, "trade_date": d, "close": price,
                              "open": price, "vol": 1000.0})
                # 000001 主力恒净流入 → resonance 可判定
                net = 1e6 if j == 0 else -1e6
                flow.append({"ts_code": c, "trade_date": d,
                             "buy_lg_amount": net, "buy_elg_amount": 0.0,
                             "sell_lg_amount": 0.0, "sell_elg_amount": 0.0})
        self._cyq = pd.DataFrame(cyq)
        self._daily = pd.DataFrame(daily)
        self._flow = pd.DataFrame(flow)

    def get_cyq_perf(self, ts_codes=None, start_date=None, end_date=None):
        return self._slice(self._cyq, start_date, end_date)

    def get_daily(self, ts_codes=None, start_date=None, end_date=None):
        return self._slice(self._daily, start_date, end_date)

    def get_moneyflow(self, ts_codes=None, start_date=None, end_date=None):
        return self._slice(self._flow, start_date, end_date)

    def get_stock_basic(self):
        rows = []
        for j in range(5):
            code = f"60000{j + 1}.SH"
            rows.append({"ts_code": code,
                         "industry": "X" if j < 2 else "Y",
                         "name": f"股{j}"})
        return pd.DataFrame(rows)

    def get_daily_basic(self, ts_codes=None, start_date=None, end_date=None):
        base = self._daily[["ts_code", "trade_date"]].copy()
        base["pe_ttm"] = [10.0 if c == "600001.SH" else 50.0
                          for c in base["ts_code"]]
        return self._slice(base, start_date, end_date)

    def _slice(self, df, start_date, end_date):
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        if start_date is not None:
            df = df[df["trade_date"] >= pd.to_datetime(start_date)]
        if end_date is not None:
            df = df[df["trade_date"] <= pd.to_datetime(end_date)]
        return df.reset_index(drop=True)


@pytest.fixture(autouse=True)
def _clean_override(monkeypatch, tmp_path):
    """测试期间覆盖文件指向临时目录，避免污染/读取真实写回。"""
    cfg = tmp_path / "config"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield
    clear_threshold_override()


def test_chip_threshold_optimize_structure_and_oos():
    svc = SignalOptimizerService(data_reader=_StubReader())
    result = svc.chip_threshold_optimize(
        months=6, signal="resonance", horizon=5,
        grid={"resonance_winner_lo": [10.0, 30.0, 50.0]},
        is_days=40, oos_days=20,
    )
    assert "error" not in result, result.get("error")
    assert result["mode"] == "chip_threshold"
    assert result["n_combos"] == 3
    assert len(result["grid_results"]) == 3
    wf = result["walk_forward"]
    assert wf["windows"], "面板持续触发共振信号，应有 walk-forward 窗口"
    assert all("best_params" in w for w in wf["windows"])
    assert wf["summary"]["n_windows"] == len(wf["windows"])
    # 000001 恒满足且恒涨 → 超额应为正
    assert wf["summary"]["oos_mean_excess"] > 0


def test_chip_threshold_apply_writes_single_source():
    svc = SignalOptimizerService(data_reader=_StubReader())
    result = svc.chip_threshold_optimize(
        months=6, signal="resonance", horizon=5,
        grid={"resonance_winner_lo": [10.0, 30.0]},
        is_days=40, oos_days=20, apply=True,
    )
    assert "applied" in result
    # 写回后 current_thresholds 与 merge（无覆盖参数）读到同一阈值
    t = current_thresholds()
    assert t.resonance_winner_lo == result["applied"]["params"]["resonance_winner_lo"]
    assert merge_thresholds(None).signature() == t.signature()
    assert merge_thresholds({}).signature() == t.signature()
    # 请求级覆盖仍然生效（叠加在写回之上）
    assert merge_thresholds({"resonance_winner_lo": 25.0}).resonance_winner_lo == 25.0
    clear_threshold_override()
    assert current_thresholds().resonance_winner_lo == SignalThresholds().resonance_winner_lo


def test_rotation_weight_optimize_and_write_back():
    svc = SignalOptimizerService(data_reader=_StubReader(240))
    result = svc.rotation_weight_optimize(
        months=9, top_n=1, rebalance_days=10,
        grid={"w_mom": [0.5, 1.0], "w_flow": [0.0, 1.0], "w_val": [0.0, 1.0]},
        is_windows=3, oos_windows=2, apply=True,
    )
    assert "error" not in result, result.get("error")
    assert result["n_combos"] == 8
    assert result["walk_forward"]["windows"]
    assert "applied" in result
    # 写回后 current_rotation_weights 与轮动服务读同一权重
    assert svc.current_rotation_weights() == result["applied"]["params"]

    from app.services.industry_rotation_service import IndustryRotationService
    # 不直接跑 _run（依赖多），只验证权重读取路径
    assert SignalOptimizerService().current_rotation_weights() == result["applied"]["params"]


def test_rotation_default_weights_without_file():
    svc = SignalOptimizerService(data_reader=_StubReader())
    assert svc.current_rotation_weights() == {"w_mom": 1.0, "w_flow": 1.0, "w_val": 1.0}
