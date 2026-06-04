from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.realtime_trading_signal_engine import RealtimeTradingSignalEngine


def _write_minute_parquet(tmp_path: Path):
    minute_dir = tmp_path / "stock_minute" / "1min" / "year=2026" / "month=06" / "day=04"
    minute_dir.mkdir(parents=True)
    rows = []
    base_time = datetime(2026, 6, 4, 9, 31)
    for idx in range(120):
        dt = base_time + timedelta(minutes=idx)
        close = 10.0 + idx * 0.05
        rows.append(
            {
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "datetime": dt,
                "open": close - 0.05,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": 1000 + idx * 20,
                "amount": (1000 + idx * 20) * close,
            }
        )
    pd.DataFrame(rows).to_parquet(minute_dir / "data.parquet", index=False)


def test_trading_signal_engine_reads_minute_history_from_parquet(tmp_path, monkeypatch):
    _write_minute_parquet(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    fake_indicator_engine = MagicMock()
    fake_indicator_engine.calculate_indicators.return_value = {
        "success": True,
        "data": {
            "MA": [None] * 118 + [[10.0, 9.5]],
            "RSI": [None] * 120,
            "MACD": [None] * 120,
            "BOLL": [None] * 120,
            "EMA": [None] * 119 + [[10.0]],
        },
    }

    engine = RealtimeTradingSignalEngine()

    with patch("app.services.realtime_trading_signal_engine.RealtimeIndicatorEngine", return_value=fake_indicator_engine), patch.object(
        engine, "_get_indicators_data", return_value={
            "MA": [{"datetime": pd.Timestamp("2026-06-04 11:30:00"), "value1": 10.0, "value2": 9.5}],
            "RSI": [{"datetime": pd.Timestamp("2026-06-04 11:30:00"), "value1": 50.0}],
            "MACD": [{"datetime": pd.Timestamp("2026-06-04 11:30:00"), "value1": 0.1, "value2": 0.05, "value3": 0.05}],
            "BOLL": [{"datetime": pd.Timestamp("2026-06-04 11:30:00"), "value1": 10.5, "value2": 10.0, "value3": 9.5}],
            "EMA": [{"datetime": pd.Timestamp("2026-06-04 11:30:00"), "value1": 10.0}],
        }
    ), patch(
        "app.services.realtime_trading_signal_engine.TradingSignal.batch_insert", return_value=(True, "ok")
    ):
        result = engine.generate_signals("000001.SZ", "1min", strategies=["ma_crossover"], lookback_days=7)
        backtest = engine.backtest_strategy("trend_following", "000001.SZ", "2026-06-04T09:31:00", "2026-06-04T11:30:00")

    assert result["success"] is True
    assert result["data"]["ts_code"] == "000001.SZ"
    assert backtest["success"] is True
    assert backtest["data"]["data_points"] == 120
