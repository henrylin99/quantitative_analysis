from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.realtime_trading_signal_engine import RealtimeTradingSignalEngine
from app.services.parquet_event_store import ParquetEventStore


def _write_minute_parquet(tmp_path: Path):
    """在动态的最近交易日写入分钟 bar。

    信号引擎按 datetime.now() - lookback_days 过滤数据，固定历史
    日期的 fixture 会随时间腐烂而失效，因此这里用"昨天"生成数据。
    """
    yesterday = datetime.now() - timedelta(days=1)
    base_time = yesterday.replace(hour=9, minute=31, second=0, microsecond=0)
    day_dir = (
        tmp_path
        / "stock_minute"
        / "1min"
        / f"year={base_time.year}"
        / f"month={base_time.month:02d}"
        / f"day={base_time.day:02d}"
    )
    day_dir.mkdir(parents=True)
    rows = []
    closes = [5.0] * 48 + [5.0, 8.0]
    for idx, close in enumerate(closes):
        dt = base_time + timedelta(minutes=idx)
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
    pd.DataFrame(rows).to_parquet(day_dir / "data.parquet", index=False)
    return base_time


def test_trading_signal_engine_generates_ma_crossover_from_parquet(tmp_path, monkeypatch):
    base_time = _write_minute_parquet(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    engine = RealtimeTradingSignalEngine()
    engine.indicator_engine.default_params["MA"]["periods"] = [5, 10]
    engine.indicator_engine.default_params["EMA"]["periods"] = [12, 26]

    with patch("app.services.realtime_trading_signal_engine.TradingSignal.batch_insert", return_value=(True, "ok")):
        engine.indicator_engine.calculate_indicators("000001.SZ", "1min", indicators=["MA", "EMA"], lookback_days=7)
        result = engine.generate_signals("000001.SZ", "1min", strategies=["ma_crossover"], lookback_days=7)

    assert result["success"] is True
    assert result["data"]["ts_code"] == "000001.SZ"
    assert result["data"]["signals_generated"] == 1
    assert result["data"]["signals"][0]["strategy_name"] == "ma_crossover"
    assert result["data"]["signals"][0]["signal_type"] == "BUY"

    stored = ParquetEventStore().get_indicators_by_time_range(
        ts_code="000001.SZ",
        period_type="1min",
        start_time=base_time.replace(hour=0, minute=0),
        end_time=(base_time + timedelta(days=1)).replace(hour=0, minute=0),
    )
    assert "sub_name" in stored.columns
    assert {"MA5", "MA10"}.issubset(set(stored["sub_name"].dropna().astype(str).unique()))
