from startup_runtime import build_health_report, build_health_summary_lines, build_startup_report


def test_build_startup_report_marks_inline_mode_as_single_script_ready():
    lines = build_startup_report(
        {
            "DATA_JOB_EXECUTION_MODE": "inline",
            "REDIS_HOST": "localhost",
            "REDIS_PORT": 6379,
            "REDIS_DB": 0,
        }
    )

    assert any("DATA_JOB_EXECUTION_MODE=inline" in line for line in lines)
    assert any("无需单独启动 Celery worker" in line for line in lines)
    assert any("主启动入口: python run.py" in line for line in lines)
    assert any("run_system.py 用于初始化与诊断" in line for line in lines)


def test_build_health_summary_lines_include_next_actions():
    report = build_health_report(
        {"DATA_JOB_EXECUTION_MODE": "inline"},
        connected=True,
        existing_tables={"data_job_run"},
    )

    lines = build_health_summary_lines(report)

    assert any("健康检查摘要:" in line for line in lines)
    assert any("主启动入口: run.py" in line for line in lines)
    assert any("推荐下一步:" in line for line in lines)
    assert any("优先执行交易日历和股票基础资料下载任务" in line for line in lines)
