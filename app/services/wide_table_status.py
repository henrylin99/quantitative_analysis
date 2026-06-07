"""
大宽表状态检查
- 判断宽表是否存在 / 是否过时
- 6PM 校验：最新交易日 18:00 后才允许更新
- 供 API 端点和 startup 调用
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# 数据源 → 分区目录映射
SOURCE_TABLES = {
    "daily_basic": "daily_basic/daily",
    "stk_factor": "stk_factor/daily",
    "moneyflow": "moneyflow/daily",
}

WIDE_TABLE_FILE = "stock_business.parquet"
TRADE_CALENDAR_FILE = "stock_trade_calendar.parquet"
CUTOFF_HOUR = 18  # 下午 6 点


def _resolve_data_dir(data_dir: Optional[str] = None) -> Path:
    if data_dir:
        return Path(data_dir)
    return Path(
        os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    )


def _get_latest_partition_date(partition_dir: Path) -> Optional[str]:
    """从 Hive 分区目录提取最新日期 (YYYY-MM-DD)。"""
    if not partition_dir.exists():
        return None
    max_date = None
    for year_dir in partition_dir.iterdir():
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        y = year_dir.name.split("=")[1]
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.startswith("month="):
                continue
            m = month_dir.name.split("=")[1]
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir() or not day_dir.name.startswith("day="):
                    continue
                d = day_dir.name.split("=")[1]
                date_str = f"{y}-{m}-{d}"
                if max_date is None or date_str > max_date:
                    max_date = date_str
    return max_date


def _is_past_cutoff(data_dir: Path) -> bool:
    """判断当前时间是否已过最新交易日的 18:00。"""
    cal_path = data_dir / TRADE_CALENDAR_FILE
    if not cal_path.exists():
        # 没有日历，默认允许
        return True

    try:
        cal = pd.read_parquet(cal_path)
    except Exception:
        return True

    open_days = cal[cal["is_open"] == 1]["cal_date"].astype(str)
    if open_days.empty:
        return True

    today_str = datetime.now().strftime("%Y%m%d")
    # 找 <= 今天 的最新交易日
    latest_open = None
    for d in sorted(open_days, reverse=True):
        if d <= today_str:
            latest_open = d
            break

    if latest_open is None:
        return False

    now = datetime.now()
    if latest_open < today_str:
        # 最新交易日是过去的日子 → 数据应已就绪
        return True
    else:
        # 今天就是最新交易日 → 检查是否过了 18:00
        return now.hour >= CUTOFF_HOUR


def get_wide_table_status(data_dir: Optional[str] = None) -> Dict[str, object]:
    """返回宽表完整状态。"""
    root = _resolve_data_dir(data_dir)
    wide_path = root / WIDE_TABLE_FILE

    # 1. 宽表自身状态
    exists = wide_path.exists() and wide_path.stat().st_size > 0
    wide_table_date = None
    if exists:
        try:
            df = pd.read_parquet(wide_path, columns=["trade_date"])
            if not df.empty:
                td = pd.to_datetime(df["trade_date"])
                wide_table_date = td.max().strftime("%Y-%m-%d")
        except Exception:
            pass

    # 2. 各数据源最新日期
    source_dates = {}
    for name, rel_path in SOURCE_TABLES.items():
        source_dates[name] = _get_latest_partition_date(root / rel_path)

    # 3. 6PM 校验
    past_cutoff = _is_past_cutoff(root)

    # 4. 是否需要更新
    should_update = False
    reason = ""

    if not exists:
        should_update = True
        reason = "宽表文件不存在"
    elif wide_table_date:
        # 任一数据源日期 > 宽表日期
        newer_sources = [
            f"{k}({v})" for k, v in source_dates.items()
            if v and v > wide_table_date
        ]
        if newer_sources:
            should_update = True
            reason = f"数据源更新: {', '.join(newer_sources)}"
        else:
            reason = "宽表已是最新"

    return {
        "exists": exists,
        "wide_table_date": wide_table_date,
        "source_dates": source_dates,
        "should_update": should_update,
        "reason": reason,
        "past_cutoff": past_cutoff,
    }


def should_update_wide_table(data_dir: Optional[str] = None) -> Tuple[bool, str]:
    """简化版，供 startup 使用。"""
    status = get_wide_table_status(data_dir)
    if not status["exists"]:
        return True, "宽表文件不存在，请在数据中心页面构建"
    if status["should_update"]:
        cutoff_note = "" if status["past_cutoff"] else "（需等待 18:00 后）"
        return True, f"数据源有更新{cutoff_note}: {status['reason']}"
    return False, f"宽表已是最新 ({status['wide_table_date']})"
