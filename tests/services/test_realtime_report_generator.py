from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.realtime_report_generator import RealtimeReportGenerator


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 5, 10, 0, 0)


class _ComparableField:
    def __init__(self, name):
        self.name = name

    def __ge__(self, other):
        return ("ge", self.name, other)

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __le__(self, other):
        return ("le", self.name, other)

    def __lt__(self, other):
        return ("lt", self.name, other)

    def __gt__(self, other):
        return ("gt", self.name, other)


class _ReportQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.extend(args)
        return self

    def all(self):
        return self.rows

    def count(self):
        return len(self.rows)


class _FakeIndicatorModel:
    id = _ComparableField("id")
    datetime = _ComparableField("datetime")
    period_type = _ComparableField("period_type")
    indicator_name = _ComparableField("indicator_name")
    query = _ReportQuery(rows=[object(), object()])


class _FakeSignal:
    created_at = _ComparableField("created_at")
    period_type = _ComparableField("period_type")
    signal_type = _ComparableField("signal_type")
    strategy_name = _ComparableField("strategy_name")

    def __init__(self, signal_type="BUY", strategy_name="trend_following", signal_strength=0.6):
        self.signal_type = signal_type
        self.strategy_name = strategy_name
        self.signal_strength = signal_strength
        self.created_at = FixedDateTime(2026, 6, 5, 9, 35)

    def to_dict(self):
        return {
            "datetime": self.created_at,
            "signal_type": self.signal_type,
            "strategy_name": self.strategy_name,
            "signal_strength": self.signal_strength,
            "period_type": "5min",
            "ts_code": "000001.SZ",
            "confidence": 0.8,
            "trigger_price": 10.0,
            "status": "ACTIVE",
        }


class _FakeSignalModel:
    created_at = _ComparableField("created_at")
    period_type = _ComparableField("period_type")
    signal_type = _ComparableField("signal_type")
    strategy_name = _ComparableField("strategy_name")
    query = _ReportQuery(rows=[_FakeSignal(signal_type="BUY", strategy_name="trend_following", signal_strength=0.7)])

    @staticmethod
    def get_signal_stats():
        return {"total_signals": 1}


class _FakeStatsQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.extend(args)
        return self

    def group_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows

    def count(self):
        return len(self.rows)


class _FakeDBSession:
    def __init__(self, indicator_rows):
        self.indicator_rows = indicator_rows

    def query(self, *args, **kwargs):
        return _FakeStatsQuery(self.indicator_rows)


class _FakeEventStore:
    def __init__(self, indicator_rows=None, signal_rows=None, minute_frame=None):
        self.indicator_rows = indicator_rows or []
        self.signal_rows = signal_rows or []
        self.minute_frame = minute_frame or pd.DataFrame()

    def get_indicators_by_time_range(self, **kwargs):
        return pd.DataFrame(self.indicator_rows)

    def get_signals_by_time_range(self, **kwargs):
        rows = []
        for row in self.signal_rows:
            if hasattr(row, "to_dict"):
                rows.append(row.to_dict())
            else:
                rows.append(row)
        return pd.DataFrame(rows)


def _write_minute_assets(tmp_path: Path):
    minute_dir = tmp_path / "stock_minute" / "5min" / "year=2026" / "month=06" / "day=05"
    minute_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "period_type": "5min",
                "datetime": FixedDateTime(2026, 6, 5, 9, 35),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 1000,
                "amount": 10100.0,
            },
            {
                "ts_code": "000002.SZ",
                "period_type": "5min",
                "datetime": FixedDateTime(2026, 6, 5, 9, 35),
                "open": 20.0,
                "high": 20.2,
                "low": 19.9,
                "close": 20.1,
                "volume": 2000,
                "amount": 40200.0,
            },
        ]
    ).to_parquet(minute_dir / "data.parquet", index=False)


def test_daily_summary_and_market_overview_use_5min_parquet(tmp_path, monkeypatch):
    _write_minute_assets(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    generator = RealtimeReportGenerator()

    fake_store = _FakeEventStore(
        indicator_rows=[
            {"indicator_name": "RSI"},
            {"indicator_name": "RSI"},
            {"indicator_name": "RSI"},
            {"indicator_name": "MACD"},
            {"indicator_name": "MACD"},
        ],
        signal_rows=[_FakeSignal(signal_type="BUY", strategy_name="trend_following", signal_strength=0.7)],
    )

    with patch.object(generator, "event_store", fake_store), patch(
        "app.services.realtime_report_generator.datetime", FixedDateTime
    ):
        daily = generator._collect_daily_summary_data()
        market = generator._collect_market_data()

    assert daily["market_data"]["minute_data_points"] == 2
    assert daily["market_data"]["active_stocks"] == 2
    assert daily["market_data"]["technical_indicators"] == 5
    assert daily["market_data"]["trading_signals"] == 1
    assert market["market_overview"]["active_stocks"] == 2
    assert market["market_overview"]["total_volume"] == 3000
    assert market["indicator_distribution"] == {"RSI": 3, "MACD": 2}


def test_signal_analysis_filters_by_five_minute_period(tmp_path, monkeypatch):
    _write_minute_assets(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    generator = RealtimeReportGenerator()
    signal_rows = [
        _FakeSignal(signal_type="BUY", strategy_name="trend_following", signal_strength=0.7),
        _FakeSignal(signal_type="SELL", strategy_name="trend_following", signal_strength=-0.5),
    ]
    fake_store = _FakeEventStore(signal_rows=signal_rows)

    with patch.object(generator, "event_store", fake_store), patch(
        "app.services.realtime_report_generator.datetime", FixedDateTime
    ):
        signal_data = generator._collect_signal_data()

    assert signal_data["signal_summary"]["total_signals"] == 2
    assert signal_data["signal_summary"]["period_type"] == "5min"


def test_generate_report_keeps_market_overview_payload_shape(tmp_path, monkeypatch):
    _write_minute_assets(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    generator = RealtimeReportGenerator()

    with patch.object(generator, "_get_or_create_template", return_value=None), patch.object(
        generator,
        "_collect_report_data",
        return_value={"market_overview": {"active_stocks": 2, "total_volume": 3000, "avg_data_points": 1.0}},
    ), patch.object(generator, "_generate_report_content", return_value={"sections": []}), patch(
        "app.services.realtime_report_generator.RealtimeReport.create_report"
    ) as create_report:
        report = create_report.return_value
        report.id = 1
        report.report_name = "mock"
        report.report_type = "market_overview"
        report.update_generation_result.return_value = None

        result = generator.generate_report("market_overview", parameters={})

    assert result["success"] is True
    assert "content" in result["data"]
    assert "data" in result["data"]
    report.update_generation_result.assert_called()


def test_daily_summary_and_market_overview_count_today_five_minute_data_only(tmp_path, monkeypatch):
    _write_minute_assets(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    generator = RealtimeReportGenerator()
    fake_store = _FakeEventStore(
        indicator_rows=[{"indicator_name": "RSI"}, {"indicator_name": "RSI"}],
        signal_rows=[_FakeSignal(signal_type="BUY", strategy_name="trend_following", signal_strength=0.7)],
    )

    with patch.object(generator, "event_store", fake_store), patch(
        "app.services.realtime_report_generator.datetime", FixedDateTime
    ):
        daily = generator._collect_daily_summary_data()
        market = generator._collect_market_data()

    assert daily["market_data"]["technical_indicators"] == 2
    assert daily["market_data"]["trading_signals"] == 1
    assert market["indicator_distribution"] == {"RSI": 2}
