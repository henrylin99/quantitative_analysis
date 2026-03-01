from collections import defaultdict
from typing import Dict, List

from app.services.data_jobs.schemas import JobDefinition


class JobRegistry:
    """Central registry for data job definitions mapped from app/utils scripts."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobDefinition] = {
            "stock_basic": JobDefinition("stock_basic", "基础资料", "app/utils/stock_basic.py"),
            "trade_calendar": JobDefinition("trade_calendar", "基础资料", "app/utils/trade_calendar.py"),
            "stock_company": JobDefinition("stock_company", "基础资料", "app/utils/stock_company.py"),
            "daily_history_by_code": JobDefinition(
                "daily_history_by_code",
                "日频行情与基本面",
                "app/utils/daily_history_by_code.py",
                dependencies=["stock_basic"],
            ),
            "daily_history_by_date": JobDefinition(
                "daily_history_by_date",
                "日频行情与基本面",
                "app/utils/daily_history_by_date.py",
                dependencies=["trade_calendar"],
            ),
            "daily_basic": JobDefinition("daily_basic", "日频行情与基本面", "app/utils/daily_basic.py"),
            "baostock_daily": JobDefinition(
                "baostock_daily",
                "日频行情与基本面",
                "app/utils/baostock_daily.py",
                dependencies=["stock_basic"],
            ),
            "min5": JobDefinition("min5", "分钟行情", "app/utils/min5.py", dependencies=["stock_basic"]),
            "min15": JobDefinition("min15", "分钟行情", "app/utils/min15.py", dependencies=["stock_basic"]),
            "min30": JobDefinition("min30", "分钟行情", "app/utils/min30.py", dependencies=["stock_basic"]),
            "min60": JobDefinition("min60", "分钟行情", "app/utils/min60.py", dependencies=["stock_basic"]),
            "income_statement": JobDefinition(
                "income_statement", "财务三表", "app/utils/income_statement.py", dependencies=["stock_basic"]
            ),
            "balance_sheet": JobDefinition(
                "balance_sheet", "财务三表", "app/utils/balance_sheet.py", dependencies=["stock_basic"]
            ),
            "cash_flow": JobDefinition(
                "cash_flow", "财务三表", "app/utils/cash_flow.py", dependencies=["stock_basic"]
            ),
            "moneyflow": JobDefinition("moneyflow", "资金流与扩展因子", "app/utils/moneyflow.py"),
            "moneyflow_ths": JobDefinition("moneyflow_ths", "资金流与扩展因子", "app/utils/moneyflow_ths.py"),
            "stk_factor": JobDefinition("stk_factor", "资金流与扩展因子", "app/utils/stk_factor.py"),
            "cyq_perf": JobDefinition("cyq_perf", "资金流与扩展因子", "app/utils/cyq_perf.py"),
            "ma_calculator": JobDefinition(
                "ma_calculator",
                "衍生计算",
                "app/utils/ma_calculator.py",
                dangerous=True,
                dependencies=["daily_history_by_code"],
            ),
        }

    def get_job(self, job_type: str) -> JobDefinition:
        if job_type not in self._jobs:
            raise KeyError(f"unknown job type: {job_type}")
        return self._jobs[job_type]

    def list_jobs(self) -> List[JobDefinition]:
        return list(self._jobs.values())

    def grouped_jobs(self) -> Dict[str, List[JobDefinition]]:
        groups: Dict[str, List[JobDefinition]] = defaultdict(list)
        for job in self._jobs.values():
            groups[job.group].append(job)
        return dict(groups)
