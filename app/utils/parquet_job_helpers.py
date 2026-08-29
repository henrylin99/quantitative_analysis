import os
import sys
import time
from datetime import datetime
from typing import List, Optional, Set, Tuple

import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader
from app.utils.parquet_writer import save_partitioned_parquet


def normalize_ymd(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    text = str(date_str).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return text
    return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_stock_codes() -> List[str]:
    reader = ParquetDataReader()
    df = reader.get_stock_basic()
    if df.empty or "ts_code" not in df.columns:
        return []
    return df["ts_code"].dropna().astype(str).tolist()


def available_open_trade_dates() -> List[str]:
    """从交易日历表读出全部开市日（YYYYMMDD，升序）。"""
    reader = ParquetDataReader()
    calendar_df = reader.get_trade_calendar()
    if calendar_df.empty or not {"cal_date", "is_open"}.issubset(calendar_df.columns):
        return []
    work_df = calendar_df.copy()
    work_df["cal_date"] = pd.to_datetime(work_df["cal_date"], errors="coerce")
    work_df = work_df.dropna(subset=["cal_date"])
    work_df["is_open"] = pd.to_numeric(work_df["is_open"], errors="coerce").fillna(0).astype(int)
    return (
        work_df.loc[work_df["is_open"] == 1, "cal_date"]
        .dt.strftime("%Y%m%d")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )


def resolve_trade_dates(default_latest_only: bool = True) -> Tuple[List[str], bool]:
    """Resolve trading dates using env vars and parquet trade calendar."""
    start_date = normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end_date = normalize_ymd(os.getenv("DATA_JOB_END_DATE"))
    trade_date = normalize_ymd(os.getenv("DATA_JOB_TRADE_DATE"))
    full_refresh = env_bool("DATA_JOB_FULL_REFRESH", default=False)

    if trade_date:
        return [trade_date], full_refresh

    available = available_open_trade_dates()

    if not available:
        if start_date and end_date and start_date <= end_date:
            if default_latest_only:
                return [end_date], full_refresh
            return [start_date], full_refresh
        return [], full_refresh

    if not end_date:
        end_date = available[-1]

    if not start_date:
        start_date = end_date if default_latest_only else available[0]

    dates = [d for d in available if start_date <= d <= end_date]
    return dates, full_refresh


def _default_data_root() -> str:
    """与 parquet_writer.save_to_parquet 一致的数据根目录解析。"""
    return os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )


def latest_partition_date(rel_table: str, data_dir: Optional[str] = None) -> Optional[str]:
    """扫描 Hive 分区目录，返回某数据集的最新分区日期（YYYYMMDD）。

    rel_table 形如 "daily_history/daily" 或 "income_statement"。
    """
    from pathlib import Path
    import re

    root = Path(data_dir) if data_dir else Path(_default_data_root())
    table_dir = root / rel_table
    if not table_dir.exists():
        return None
    dates = []
    for match in table_dir.rglob("day=*"):
        found = re.search(r"year=(\d{4}).*month=(\d{2}).*day=(\d{2})", str(match))
        if found:
            dates.append("".join(found.groups()))
    return max(dates) if dates else None


def existing_partition_dates(rel_table: str, data_dir: Optional[str] = None) -> Set[str]:
    """扫描某数据集的全部已有分区日期（YYYYMMDD 集合）。"""
    from pathlib import Path
    import re

    root = Path(data_dir) if data_dir else Path(_default_data_root())
    table_dir = root / rel_table
    if not table_dir.exists():
        return set()
    dates: Set[str] = set()
    for match in table_dir.rglob("day=*"):
        found = re.search(r"year=(\d{4}).*month=(\d{2}).*day=(\d{2})", str(match))
        if found:
            dates.add("".join(found.groups()))
    return dates


def _max_gap_fill_days() -> int:
    try:
        value = int(os.getenv("DATA_JOB_MAX_GAP_FILL", "60"))
    except ValueError:
        return 60
    return value if value > 0 else 60


def resolve_trade_dates_with_gap_fill(rel_table: str, data_dir: Optional[str] = None) -> Tuple[List[str], bool]:
    """带缺口回补的交易日解析（日更作业用）。

    显式传 DATA_JOB_TRADE_DATE/_START_DATE/_END_DATE 或 FULL_REFRESH 时
    与 resolve_trade_dates 行为一致；缺省模式下不再只拉最新一天——
    那样漏跑一天就是永久空洞。改为用交易日历对本地已有分区做差集：
    回补 [最早分区, 最新交易日] 内的所有缺失日。最早分区之前的日期
    属于历史基线，不自动回补（需要全量请显式传区间或 FULL_REFRESH）。
    单次回补天数上限 DATA_JOB_MAX_GAP_FILL（默认 60），超限时从旧往新
    截断并提示，防止误删分区后一次性烧光 API 配额。
    """
    explicit = (
        any(os.getenv(key) for key in ("DATA_JOB_TRADE_DATE", "DATA_JOB_START_DATE", "DATA_JOB_END_DATE"))
        or env_bool("DATA_JOB_FULL_REFRESH", default=False)
    )
    dates, full_refresh = resolve_trade_dates(default_latest_only=True)
    if explicit or full_refresh or not dates:
        return dates, full_refresh

    have = existing_partition_dates(rel_table, data_dir=data_dir)
    if not have:
        # 本地还没有该表：保持"首跑只拉最新一天"，历史由显式区间负责
        return dates, full_refresh

    available = available_open_trade_dates()
    if not available:
        return dates, full_refresh

    latest = dates[-1]
    first_have = min(have)
    missing = [d for d in available if first_have <= d <= latest and d not in have]
    if not missing:
        return dates, full_refresh

    cap = _max_gap_fill_days()
    if len(missing) > cap:
        dropped_count = len(missing) - cap
        missing = missing[-cap:]
        print(
            f"[gap_fill:{rel_table}] 检测到 {len(missing) + dropped_count} 个缺失交易日，"
            f"超过单次回补上限 {cap}，本轮只回补最近 {cap} 天；"
            "更早的缺口请显式传 DATA_JOB_START_DATE/_END_DATE 回补"
        )
    print(f"[gap_fill:{rel_table}] 回补缺失交易日: {missing[0]} ~ {missing[-1]} 共 {len(missing)} 天")
    return missing, False


class DailyFetchJob:
    """按交易日拉全市场数据的作业骨架。

    统一收口此前在每个抓取脚本里复制粘贴的主循环：缺口回补的
    交易日解析、接口限速、指数退避重试、分区落盘、失败退出码。
    子类只需声明 job_name / rel_table / fetch_one()。

    重试后仍失败的交易日会让 run() 以退出码 1 结束：作业被记为
    failed 可整体重试，漏掉的日子由下一轮 gap_fill 自动补上；
    若静默成功，缺失就成了没人知道的永久空洞。
    """

    job_name: str = ""
    rel_table: str = ""
    #: 单次接口调用后的限速间隔（秒），tushare 按积分限速，按接口松紧覆盖
    rate_limit_seconds: float = 0.12
    #: 单日拉取的最大尝试次数（指数退避）
    max_retries: int = 3

    def __init__(self, api=None):
        self.api = api

    def fetch_one(self, trade_date: str) -> pd.DataFrame:
        """拉取单个交易日的全市场数据，子类实现。"""
        raise NotImplementedError

    def _fetch_with_retry(self, trade_date: str) -> Optional[pd.DataFrame]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                df = self.fetch_one(trade_date)
                if self.rate_limit_seconds > 0:
                    time.sleep(self.rate_limit_seconds)
                return df
            except Exception as exc:  # noqa: BLE001 - 网络/权限异常统一退避重试
                last_error = exc
                if attempt >= self.max_retries:
                    break
                backoff = max(self.rate_limit_seconds, 0.5) * (2 ** (attempt - 1))
                logger.warning(
                    f"[{self.job_name}] {trade_date} 第 {attempt} 次拉取失败: {exc}，{backoff:.1f}s 后重试"
                )
                time.sleep(backoff)
        logger.error(f"[{self.job_name}] {trade_date} 重试 {self.max_retries} 次仍失败: {last_error}")
        return None

    def run(self) -> int:
        trade_dates, _ = resolve_trade_dates_with_gap_fill(self.rel_table)
        if not trade_dates:
            print(f"[{self.job_name}] 没有需要拉取的交易日")
            return 0

        total_saved = 0
        failed_dates: List[str] = []
        for trade_date in trade_dates:
            print(f"[{self.job_name}] trade_date={trade_date}")
            df = self._fetch_with_retry(trade_date)
            if df is None:
                failed_dates.append(trade_date)
                continue
            total_saved += save_partitioned_parquet(df, "trade_date", self.rel_table)

        print(f"[{self.job_name}] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}")
        if failed_dates:
            print(f"[{self.job_name}] 以下交易日重试后仍失败: {failed_dates}")
            sys.exit(1)
        return total_saved
