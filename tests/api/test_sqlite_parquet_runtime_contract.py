from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from flask import Flask

from app.api.realtime_indicators import realtime_indicators_bp


class _BlockedQuery:
    def filter(self, *args, **kwargs):
        raise AssertionError("indicator flow should not touch ORM-backed storage")


class _BlockedRealtimeIndicator:
    query = _BlockedQuery()

    @staticmethod
    def batch_insert(*args, **kwargs):
        raise AssertionError("indicator flow should not write through ORM-backed storage")


def _write_minute_parquet(root: Path) -> None:
    """在动态的最近交易日写入分钟 bar。

    计算链路按 datetime.now() - lookback_days 过滤数据，固定历史
    日期的 fixture 会随时间腐烂而失效，因此用"昨天"生成数据。
    """
    yesterday = datetime.now() - timedelta(days=1)
    base_time = yesterday.replace(hour=9, minute=31, second=0, microsecond=0)
    minute_dir = (
        root
        / "stock_minute"
        / "1min"
        / f"year={base_time.year}"
        / f"month={base_time.month:02d}"
        / f"day={base_time.day:02d}"
    )
    minute_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx in range(60):
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


def _build_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(realtime_indicators_bp, url_prefix="/api/realtime-analysis/indicators")
    return app


def test_indicator_calculation_runs_without_orm_backed_mysql_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_minute_parquet(tmp_path)

    with patch("app.services.realtime_indicator_engine.RealtimeIndicator", _BlockedRealtimeIndicator):
        with _build_app().test_client() as client:
            response = client.post(
                "/api/realtime-analysis/indicators/calculate",
                json={
                    "ts_code": "000001.SZ",
                    "period_type": "1min",
                    "indicators": ["RSI"],
                    "lookback_days": 7,
                },
            )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["stored_records"] > 0
