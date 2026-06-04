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


def test_indicator_engine_reads_minute_history_from_parquet(tmp_path, monkeypatch):
    minute_dir = Path(tmp_path) / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    minute_dir.mkdir(parents=True)
    rows = []
    for idx in range(20):
        minute = 31 + idx
        close = 10.1 + idx * 0.1
        rows.append(
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": f"2026-06-04T09:{minute:02d}:00",
                "open": close - 0.1,
                "high": close + 0.1,
                "low": close - 0.2,
                "close": close,
                "volume": 1000 + idx * 100,
                "amount": (1000 + idx * 100) * close,
            }
        )
    pd.DataFrame(rows).to_parquet(minute_dir / "data.parquet", index=False)

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    _FakeRealtimeIndicator.query.filter.return_value.delete.return_value = 0

    engine = RealtimeIndicatorEngine()

    with patch("app.services.realtime_indicator_engine.RealtimeIndicator", _FakeRealtimeIndicator):
        result = engine.calculate_indicators("000001.SZ", "1min", indicators=["RSI"], lookback_days=7)

    assert result["success"] is True
    assert result["data_points"] == 20
    assert result["stored_records"] > 0
