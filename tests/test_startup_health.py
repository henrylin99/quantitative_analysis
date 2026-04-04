from startup_runtime import build_health_report


def test_build_health_report_marks_missing_tables_and_standard_entrypoint():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "inline"},
        connected=True,
        existing_tables={"data_job_run", "stock_daily_basic"},
    )

    assert report["entrypoint"] == "run.py"
    assert report["database"]["ok"] is False
    assert report["database"]["missing_tables"] == [
        "stock_basic",
        "stock_trade_calendar",
    ]
    assert report["data_jobs"]["execution_mode"] == "inline"


def test_build_health_report_marks_database_ok_when_required_tables_exist():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "celery"},
        connected=True,
        existing_tables={"stock_basic", "stock_trade_calendar", "data_job_run"},
    )

    assert report["database"]["ok"] is True
    assert report["database"]["missing_tables"] == []


def test_build_health_report_marks_empty_core_tables():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "inline"},
        connected=True,
        existing_tables={"stock_basic", "stock_trade_calendar", "data_job_run"},
        non_empty_tables={"data_job_run"},
    )

    assert report["database"]["empty_tables"] == ["stock_basic", "stock_trade_calendar"]
    assert "优先执行交易日历和股票基础资料下载任务" in report["database"]["next_actions"][0]
