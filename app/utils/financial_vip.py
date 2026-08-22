"""财务三张表 VIP 接口下载（income_vip / balancesheet_vip / cashflow_vip）。

vip 接口按报告期（period）一次调用返回全市场数据，替代旧的逐只循环
（5000+ 次调用），并支持增量：
- 默认从本地最新报告期（含）重新拉取到最新报告期，覆盖财报更正数据
- DATA_JOB_START_DATE / DATA_JOB_END_DATE 显式指定报告期窗口
- DATA_JOB_FULL_REFRESH=1 时从 20200101 全量拉取
"""

import os
from datetime import datetime
from typing import List, Optional, Tuple

from job_env import env_bool, normalize_ymd
from parquet_job_helpers import latest_partition_date
from parquet_writer import save_partitioned_parquet

QUARTER_ENDS = ("0331", "0630", "0930", "1231")
HISTORY_BASELINE = "20200101"


def quarter_periods(start_ymd: str, end_ymd: str) -> List[str]:
    """生成 [start, end] 之间的全部季度报告期（YYYYMMDD）。"""
    periods = []
    for year in range(int(start_ymd[:4]), int(end_ymd[:4]) + 1):
        for month_day in QUARTER_ENDS:
            period = f"{year}{month_day}"
            if start_ymd <= period <= end_ymd:
                periods.append(period)
    return periods


def resolve_report_periods(
    table: str,
    data_dir: Optional[str] = None,
    today: Optional[str] = None,
) -> Tuple[List[str], bool]:
    """解析本次需要拉取的报告期列表与是否全量刷新。"""
    start_date = normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end_date = normalize_ymd(os.getenv("DATA_JOB_END_DATE"))
    full_refresh = env_bool("DATA_JOB_FULL_REFRESH", default=False)
    today = today or datetime.now().strftime("%Y%m%d")

    if not end_date:
        end_date = today
    if not start_date:
        if full_refresh:
            start_date = HISTORY_BASELINE
        else:
            # 从本地最新报告期（含）重拉，覆盖该期财报的后续更正
            start_date = latest_partition_date(table, data_dir=data_dir) or HISTORY_BASELINE

    return quarter_periods(start_date, end_date), full_refresh


def _fetch_period(api, api_name: str, period: str, fields: List[str]):
    try:
        return api(period=period, fields=fields)
    except Exception as exc:
        message = str(exc)
        if "权限" in message or "积分" in message:
            raise ValueError(
                f"{api_name} 接口需要 Tushare VIP 权限（当前 TOKEN 积分不足）：{message}"
            ) from exc
        raise


def run_financial_vip_job(api_name: str, table: str, fields: List[str]) -> None:
    """按报告期批量调用 vip 接口并按 end_date 分区落盘。"""
    from db_utils import DatabaseUtils

    periods, _ = resolve_report_periods(table)
    if not periods:
        print(f"[{table}] 无需更新：窗口内没有报告期")
        return

    pro = DatabaseUtils.init_tushare_api()
    api = getattr(pro, api_name, None)
    if api is None:
        raise ValueError(f"当前 Tushare 客户端不支持 {api_name} 接口")

    total_saved = 0
    for period in periods:
        df = _fetch_period(api, api_name, period, fields)
        rows = 0 if df is None or df.empty else len(df)
        total_saved += save_partitioned_parquet(df, "end_date", table)
        print(f"[{table}] period={period} rows={rows}")

    print(f"[{table}] 完成，periods={periods}, total_upsert={total_saved}")
