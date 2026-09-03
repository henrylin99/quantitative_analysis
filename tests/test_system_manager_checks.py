from startup_runtime import PARQUET_ASSETS

from run_system import SystemManager


def test_system_manager_builds_health_summary_from_existing_assets():
    manager = SystemManager()

    report = manager.build_health_summary(
        connected=True,
        existing_tables={"stock_basic.parquet", "daily_history/daily"},
    )

    assert report["entrypoint"] == "run.py"
    assert report["database"]["ok"] is False
    assert "stock_trade_calendar.parquet" in report["database"]["missing_tables"]


def test_system_manager_health_summary_marks_database_ok_when_core_assets_exist():
    manager = SystemManager()

    report = manager.build_health_summary(
        connected=True,
        existing_tables=set(PARQUET_ASSETS),
    )

    assert report["database"]["ok"] is True


def test_system_manager_health_summary_reports_empty_assets():
    manager = SystemManager()

    report = manager.build_health_summary(
        connected=True,
        existing_tables=set(PARQUET_ASSETS),
        non_empty_tables={"daily_history/daily"},
    )

    assert "stock_basic.parquet" in report["database"]["empty_tables"]
    assert "stock_trade_calendar.parquet" in report["database"]["empty_tables"]
    assert report["database"]["next_actions"]
