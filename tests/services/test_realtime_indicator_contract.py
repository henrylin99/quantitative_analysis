from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.realtime_indicator_engine import RealtimeIndicatorEngine


class _ComparableField:
    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self


class _FakeRealtimeIndicator:
    ts_code = _ComparableField()
    period_type = _ComparableField()
    datetime = _ComparableField()
    query = MagicMock()

    @staticmethod
    def batch_insert(_rows):
        return True, "ok"


def _write_minute_bars(tmp_path, ts_code, n_bars, base_dt=None):
    """在动态的最近交易日写入分钟 bar。

    引擎按 datetime.now() - lookback_days 过滤，测试数据必须落在
    当前时间附近——固定历史日期的 fixture 会随时间腐烂而失效。
    """
    if base_dt is None:
        yesterday = datetime.now() - timedelta(days=1)
        base_dt = yesterday.replace(hour=9, minute=31, second=0, microsecond=0)

    day_dir = (
        Path(tmp_path)
        / "stock_minute"
        / "1min"
        / f"year={base_dt.year}"
        / f"month={base_dt.month:02d}"
        / f"day={base_dt.day:02d}"
    )
    day_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx in range(n_bars):
        close = 10.0 + idx * 0.1
        rows.append(
            {
                "ts_code": ts_code,
                "period_type": "1min",
                "datetime": base_dt + timedelta(minutes=idx),
                "open": close - 0.1,
                "high": close + 0.1,
                "low": close - 0.2,
                "close": close,
                "volume": 1000 + idx * 100,
                "amount": (1000 + idx * 100) * close,
            }
        )
    pd.DataFrame(rows).to_parquet(day_dir / "data.parquet", index=False)
    return base_dt


def test_indicator_engine_reads_minute_history_from_parquet(tmp_path, monkeypatch):
    _write_minute_bars(tmp_path, "000001.SZ", 20)

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    _FakeRealtimeIndicator.query.filter.return_value.delete.return_value = 0

    engine = RealtimeIndicatorEngine()

    with patch("app.services.realtime_indicator_engine.RealtimeIndicator", _FakeRealtimeIndicator):
        result = engine.calculate_indicators("000001.SZ", "1min", indicators=["RSI"], lookback_days=7)

    assert result["success"] is True
    assert result["data_points"] == 20
    assert result["stored_records"] > 0


def test_indicator_engine_persists_ma_rows_with_sub_names(tmp_path, monkeypatch):
    _write_minute_bars(tmp_path, "000001.SZ", 30)

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    engine = RealtimeIndicatorEngine()
    engine.default_params["MA"]["periods"] = [5, 10]

    with patch("app.services.realtime_indicator_engine.RealtimeIndicator", _FakeRealtimeIndicator), patch(
        "app.services.realtime_indicator_engine.RealtimeIndicator.batch_insert", return_value=(True, "ok")
    ) as batch_insert:
        result = engine.calculate_indicators("000001.SZ", "1min", indicators=["MA"], lookback_days=7)

    assert result["success"] is True
    inserted = batch_insert.call_args.args[0]
    assert any(row["indicator_name"] == "MA" and row["sub_name"] == "MA5" for row in inserted)
    assert any(row["indicator_name"] == "MA" and row["sub_name"] == "MA10" for row in inserted)
