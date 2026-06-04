from unittest.mock import patch

import pandas as pd

from app.services.realtime_data_manager import RealtimeDataManager


def test_realtime_data_manager_stock_list_comes_from_parquet_basic_table():
    manager = RealtimeDataManager()

    with patch.object(manager.data_reader, "get_stock_basic") as get_stock_basic:
        get_stock_basic.return_value = pd.DataFrame(
            {"ts_code": ["000001.SZ", "000002.SZ"], "name": ["平安银行", "万科A"]}
        )
        result = manager.get_stock_list_from_db()

    assert result == ["000001.SZ", "000002.SZ"]


def test_realtime_data_manager_summary_and_stats_delegate_to_minute_reader():
    manager = RealtimeDataManager()
    fake_reader = manager.get_minute_reader()

    with patch.object(fake_reader, "get_summary") as get_summary, patch.object(
        fake_reader, "get_data"
    ) as get_data:
        get_summary.return_value = {
            "has_data": True,
            "data_count": 2,
            "latest_time": "2026-06-04T09:31:00",
            "earliest_time": "2026-06-04T09:30:00",
            "missing_count": 0,
            "completeness": 100.0,
            "status": "ok",
            "message": "数据完整性: 100.0%",
        }
        get_data.side_effect = [
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "datetime": [pd.Timestamp("2026-06-04 09:31:00"), pd.Timestamp("2026-06-04 09:31:00")],
                    "pct_chg": [1.0, -1.0],
                    "volume": [100, 200],
                    "amount": [1000.0, 2000.0],
                }
            ),
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "datetime": [pd.Timestamp("2026-06-04 09:31:00")],
                    "pct_chg": [1.0],
                    "volume": [100],
                    "amount": [1000.0],
                }
            ),
            pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "datetime": [pd.Timestamp("2026-06-04 09:31:00")],
                    "pct_chg": [1.0],
                    "volume": [100],
                    "amount": [1000.0],
                }
            ),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
        ]

        summary = manager.get_minute_summary("000001.SZ", "1min", 24)
        stats = manager.get_minute_stats()

    assert summary["status"] == "ok"
    assert summary["data_count"] == 2
    assert stats["period_stats"]["1min"] == 2
    assert stats["total_stocks"] == 2
