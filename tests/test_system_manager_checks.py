from run_system import SystemManager


def test_system_manager_builds_health_summary_from_existing_tables():
    manager = SystemManager()

    report = manager.build_health_summary(
        connected=True,
        existing_tables={"data_job_run", "stock_basic"},
    )

    assert report["entrypoint"] == "run.py"
    assert report["database"]["ok"] is False
    assert report["database"]["missing_tables"] == ["stock_trade_calendar"]


def test_system_manager_health_summary_marks_database_ok_when_core_tables_exist():
    manager = SystemManager()

    report = manager.build_health_summary(
        connected=True,
        existing_tables={"data_job_run", "stock_basic", "stock_trade_calendar"},
    )

    assert report["database"]["ok"] is True
