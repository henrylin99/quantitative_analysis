"""实时指标复权合约：除权除息窗口内不得出现假跳空驱动的历史 bar。"""
import pandas as pd
import numpy as np
import pytest

from app.services.realtime_indicator_engine import RealtimeIndicatorEngine


def _engine_with_prices(hfq: pd.DataFrame, raw: pd.DataFrame) -> RealtimeIndicatorEngine:
    engine = RealtimeIndicatorEngine.__new__(RealtimeIndicatorEngine)

    class _FakeReader:
        def get_return_prices(self, ts_codes=None, start_date=None, end_date=None):
            return hfq.copy()

        def get_daily(self, ts_codes=None, start_date=None, end_date=None):
            return raw.copy()

    engine.data_reader = _FakeReader()
    return engine


def _minute_frame():
    day1 = pd.Timestamp(2026, 6, 1, 10, 0)
    day2 = pd.Timestamp(2026, 6, 2, 10, 0)
    return pd.DataFrame(
        [
            {"datetime": day1, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
            {"datetime": day2, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        ]
    )


def test_ex_div_gap_is_scaled_out_but_latest_day_unchanged():
    """day1 复权比 1.0、day2 复权比 1.1（其间分红）。以最新日归一后：
    day1 bar 被缩放（跳空被抹平），day2（最新）保持盘面原价。"""
    raw = pd.DataFrame(
        [
            {"trade_date": pd.Timestamp(2026, 6, 1), "close": 100.0},
            {"trade_date": pd.Timestamp(2026, 6, 2), "close": 100.0},
        ]
    )
    hfq = raw.copy()
    hfq.loc[hfq["trade_date"] == pd.Timestamp(2026, 6, 2), "close"] = 110.0
    engine = _engine_with_prices(hfq, raw)

    out = engine._adjust_minute_prices("000001.SZ", _minute_frame())

    assert out["close"].iloc[1] == pytest.approx(100.0)
    assert out["close"].iloc[0] == pytest.approx(100.0 / 1.1)
    assert out["high"].iloc[0] == pytest.approx(101.0 / 1.1)


def test_window_without_corporate_action_is_bitwise_unchanged():
    """窗口内无除权事件（最常见情形）时数值必须与未复权完全一致。"""
    raw = pd.DataFrame(
        [
            {"trade_date": pd.Timestamp(2026, 6, 1), "close": 100.0},
            {"trade_date": pd.Timestamp(2026, 6, 2), "close": 100.0},
        ]
    )
    engine = _engine_with_prices(raw.copy(), raw)

    original = _minute_frame()
    out = engine._adjust_minute_prices("000001.SZ", original)

    assert np.allclose(out["close"].to_numpy(), original["close"].to_numpy())
    assert np.allclose(out["open"].to_numpy(), original["open"].to_numpy())


def test_price_source_failure_degrades_to_unadjusted():
    engine = _engine_with_prices(pd.DataFrame(), pd.DataFrame())
    original = _minute_frame()

    out = engine._adjust_minute_prices("000001.SZ", original)

    assert out is original, "价格源缺失时应原样返回，不得破坏原始数据"
