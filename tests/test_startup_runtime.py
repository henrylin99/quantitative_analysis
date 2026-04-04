from startup_runtime import build_startup_report


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
