from startup_runtime import build_health_report, PARQUET_ASSETS


def test_build_health_report_marks_missing_parquet_assets_and_standard_entrypoint():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "inline"},
        connected=True,
        existing_tables={"stock_daily_basic"},
    )

    assert report["entrypoint"] == "run.py"
    assert report["database"]["ok"] is False
    # Core parquet assets should be reported as missing
    assert "stock_basic.parquet" in report["database"]["missing_tables"]
    assert "stock_trade_calendar.parquet" in report["database"]["missing_tables"]
    assert report["data_jobs"]["execution_mode"] == "inline"


def test_build_health_report_marks_database_ok_when_required_assets_exist():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "celery"},
        connected=True,
        existing_tables=set(PARQUET_ASSETS),
    )

    assert report["database"]["ok"] is True
    assert report["database"]["missing_tables"] == []


def test_build_health_report_marks_empty_core_parquet_assets():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "inline"},
        connected=True,
        existing_tables=set(PARQUET_ASSETS),
        non_empty_tables={"daily_history/daily"},
    )

    assert "stock_basic.parquet" in report["database"]["empty_tables"]
    assert "stock_trade_calendar.parquet" in report["database"]["empty_tables"]
    assert "优先执行交易日历和股票基础资料下载任务" in report["database"]["next_actions"][0]
