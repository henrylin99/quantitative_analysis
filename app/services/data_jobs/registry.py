from collections import defaultdict
from typing import Dict, List, Set

from app.services.data_jobs.schemas import JobDefinition


class JobRegistry:
    """Central registry for data job definitions mapped from app/utils scripts."""

    def __init__(self) -> None:
        # 仅向页面暴露的任务（按用户确认保留）
        self._visible_job_types: Set[str] = {
            "stock_basic",            # 1
            "trade_calendar",         # 2
            "stock_company",          # 3
            "daily_history_by_date",  # 5
            "daily_basic",            # 6
            "moneyflow",              # 15
            "stk_factor",             # 17
            "cyq_perf",               # 18
        }

        self._jobs: Dict[str, JobDefinition] = {
            "stock_basic": JobDefinition(
                "stock_basic",
                "基础资料",
                "app/utils/stock_basic.py",
                display_name="股票基础资料",
                description="下载股票代码、简称、地域、行业和上市日期。",
                recommended_order=2,
                source_name="tushare",
                source_mode="full",
            ),
            "trade_calendar": JobDefinition(
                "trade_calendar",
                "基础资料",
                "app/utils/trade_calendar.py",
                display_name="交易日历",
                description="下载交易日、开市状态和前一交易日，是日频任务的基础依赖。",
                recommended_order=1,
                source_name="tushare",
                source_mode="incremental",
                supports_incremental=True,
            ),
            "stock_company": JobDefinition(
                "stock_company",
                "基础资料",
                "app/utils/stock_company.py",
                display_name="上市公司资料",
                description="补充公司基本信息和上市主体信息。",
                recommended_order=3,
                source_name="tushare",
                source_mode="full",
            ),
            "daily_history_by_code": JobDefinition(
                "daily_history_by_code",
                "日频行情与基本面",
                "app/utils/daily_history_by_code.py",
                display_name="日线行情（按股票代码）",
                description="按股票逐只下载日线行情，依赖股票基础资料。",
                dependencies=["stock_basic"],
                recommended_order=5,
                source_name="tushare",
                source_mode="incremental",
                supports_incremental=True,
            ),
            "daily_history_by_date": JobDefinition(
                "daily_history_by_date",
                "日频行情与基本面",
                "app/utils/daily_history_by_date.py",
                display_name="日线行情（按交易日）",
                description="按交易日批量下载日线行情，适合初始化全市场日线数据。",
                dependencies=["trade_calendar"],
                recommended_order=4,
                source_name="tushare",
                source_mode="incremental",
                supports_incremental=True,
            ),
            "daily_basic": JobDefinition(
                "daily_basic",
                "日频行情与基本面",
                "app/utils/daily_basic.py",
                display_name="日线基本指标",
                description="下载换手率、市盈率、市值等日线基本面指标。",
                recommended_order=6,
                source_name="tushare",
                source_mode="incremental",
                supports_incremental=True,
            ),
            "baostock_daily": JobDefinition(
                "baostock_daily",
                "日频行情与基本面",
                "app/utils/baostock_daily.py",
                display_name="Baostock 日线",
                description="使用 Baostock 补充日线行情数据。",
                dependencies=["stock_basic"],
                recommended_order=7,
                source_name="baostock",
                source_mode="incremental",
                supports_incremental=True,
            ),
            "min5": JobDefinition("min5", "分钟行情", "app/utils/min5.py", display_name="5 分钟行情", description="下载 5 分钟级别行情。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True),
            "min15": JobDefinition("min15", "分钟行情", "app/utils/min15.py", display_name="15 分钟行情", description="下载 15 分钟级别行情。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True),
            "min30": JobDefinition("min30", "分钟行情", "app/utils/min30.py", display_name="30 分钟行情", description="下载 30 分钟级别行情。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True),
            "min60": JobDefinition("min60", "分钟行情", "app/utils/min60.py", display_name="60 分钟行情", description="下载 60 分钟级别行情。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True),
            "income_statement": JobDefinition(
                "income_statement", "财务三表", "app/utils/income_statement.py", display_name="利润表", description="下载上市公司利润表。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True
            ),
            "balance_sheet": JobDefinition(
                "balance_sheet", "财务三表", "app/utils/balance_sheet.py", display_name="资产负债表", description="下载上市公司资产负债表。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True
            ),
            "cash_flow": JobDefinition(
                "cash_flow", "财务三表", "app/utils/cash_flow.py", display_name="现金流量表", description="下载上市公司现金流量表。", dependencies=["stock_basic"], source_name="tushare", source_mode="incremental", supports_incremental=True
            ),
            "moneyflow": JobDefinition("moneyflow", "资金流与扩展因子", "app/utils/moneyflow.py", display_name="资金流向", description="下载主力、大单、中单和小单资金流数据。", recommended_order=7, source_name="tushare", source_mode="incremental", supports_incremental=True),
            "moneyflow_ths": JobDefinition("moneyflow_ths", "资金流与扩展因子", "app/utils/moneyflow_ths.py", display_name="同花顺资金流", description="下载同花顺口径资金流数据。", source_name="ths", source_mode="incremental", supports_incremental=True),
            "stk_factor": JobDefinition("stk_factor", "资金流与扩展因子", "app/utils/stk_factor.py", display_name="扩展技术因子", description="下载或计算扩展因子字段。", recommended_order=8, source_name="tushare", source_mode="incremental", supports_incremental=True),
            "cyq_perf": JobDefinition("cyq_perf", "资金流与扩展因子", "app/utils/cyq_perf.py", display_name="筹码分布", description="下载筹码成本、胜率等筹码分布指标。", recommended_order=9, source_name="tushare", source_mode="incremental", supports_incremental=True),
            "ma_calculator": JobDefinition(
                "ma_calculator",
                "衍生计算",
                "app/utils/ma_calculator.py",
                display_name="均线衍生计算",
                description="基于日线行情生成均线结果，属于衍生计算任务。",
                dangerous=True,
                dependencies=["daily_history_by_code"],
                source_name="derived",
                source_mode="derived",
            ),
        }

    def get_job(self, job_type: str) -> JobDefinition:
        if job_type not in self._jobs:
            raise KeyError(f"unknown job type: {job_type}")
        return self._jobs[job_type]

    def list_jobs(self) -> List[JobDefinition]:
        return list(self._jobs.values())

    def list_visible_jobs(self) -> List[JobDefinition]:
        jobs = [job for job in self._jobs.values() if job.job_type in self._visible_job_types]
        return sorted(jobs, key=lambda job: (job.recommended_order, job.group, job.job_type))

    def grouped_jobs(self) -> Dict[str, List[JobDefinition]]:
        groups: Dict[str, List[JobDefinition]] = defaultdict(list)
        for job in self._jobs.values():
            groups[job.group].append(job)
        return dict(groups)
