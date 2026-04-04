from app.services.realtime_data_manager import RealtimeDataManager


def test_legacy_minute_sync_is_disabled_for_production_path(app):
    manager = RealtimeDataManager()

    result = manager._sync_minute_data_legacy("000001.SZ", "2024-01-01", "2024-01-05", "1min")

    assert result["success"] is False
    assert "legacy" in result["message"].lower() or "已禁用" in result["message"]


def test_batch_sync_rejects_legacy_mode(app):
    manager = RealtimeDataManager()

    result = manager.sync_multiple_stocks_data(
        ["000001.SZ", "000002.SZ"],
        use_baostock=False,
    )

    assert result["success"] is False
    assert "legacy" in result["message"].lower() or "真实数据源" in result["message"]


def test_sync_all_periods_rejects_legacy_mode(app):
    manager = RealtimeDataManager()

    result = manager.sync_all_periods_for_stock(
        "000001.SZ",
        use_baostock=False,
    )

    assert result["success"] is False
    assert "legacy" in result["message"].lower() or "真实数据源" in result["message"]
