from unittest.mock import MagicMock

from app.services.realtime_data_manager import RealtimeDataManager


def test_sync_minute_data_dispatches_to_tongdaxin_service():
    manager = RealtimeDataManager()
    manager.tongdaxin_minute_sync_service = MagicMock()
    manager.tongdaxin_minute_sync_service.__enter__.return_value = manager.tongdaxin_minute_sync_service
    manager.tongdaxin_minute_sync_service.sync_single_stock_data.return_value = {"success": True}

    result = manager.sync_minute_data(
        "sh.600000",
        "2026-06-05",
        "2026-06-05",
        "5min",
        use_baostock=True,
        data_source="tongdaxin",
    )

    assert result["success"] is True
    manager.tongdaxin_minute_sync_service.sync_single_stock_data.assert_called_once()
