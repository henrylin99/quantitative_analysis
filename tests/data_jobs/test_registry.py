import pytest

from app.services.data_jobs.registry import JobRegistry

pytestmark = pytest.mark.module_data_jobs


def test_registry_contains_all_utils_jobs():
    registry = JobRegistry()
    jobs = registry.list_jobs()
    job_types = {job.job_type for job in jobs}

    assert len(jobs) >= 16
    assert "stock_basic" in job_types
    assert "income_statement" in job_types
    # baostock_daily/min* 脚本硬编码日期区间且产出的表无消费方，已摘除注册，
    # 防止 AI 工具/API 误提交无效作业
    assert "baostock_daily" not in job_types
    assert "min5" not in job_types
    assert "min15" not in job_types
    assert "min30" not in job_types
    assert "min60" not in job_types


def test_registry_visible_jobs_follow_whitelist():
    registry = JobRegistry()
    jobs = registry.list_visible_jobs()
    job_types = [job.job_type for job in jobs]

    assert len(job_types) == 10
    assert job_types == [
        "trade_calendar",
        "stock_basic",
        "stock_company",
        "daily_history_by_date",
        "daily_basic",
        "moneyflow",
        "stk_factor",
        "cyq_perf",
        "wide_table_builder",
        "factor_compute",
    ]


def test_factor_compute_job_is_derived_with_data_dependencies():
    """因子计算必须是衍生作业，且依赖全部上游数据作业。"""
    registry = JobRegistry()
    job = registry.get_job("factor_compute")

    assert job.source_mode == "derived"
    assert job.script_path == "app/utils/factor_compute.py"
    for dependency in (
        "daily_history_by_code", "daily_basic", "stk_factor",
        "moneyflow", "cyq_perf", "income_statement", "balance_sheet",
    ):
        assert dependency in job.dependencies, f"缺少上游依赖: {dependency}"
