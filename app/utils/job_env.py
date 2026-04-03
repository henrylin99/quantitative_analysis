import os
from datetime import datetime, timedelta
from typing import Optional


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


def latest_open_trade_date(cursor) -> Optional[str]:
    cursor.execute(
        """
        SELECT DATE_FORMAT(MAX(cal_date), '%Y%m%d')
        FROM stock_trade_calendar
        WHERE is_open = 1 AND cal_date <= CURDATE()
        """
    )
    return cursor.fetchone()[0]


def next_date_ymd(date_ymd: str) -> str:
    return (datetime.strptime(date_ymd, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")


def resolve_date_window(cursor, target_table: str) -> tuple[Optional[str], Optional[str], bool]:
    start_date = normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end_date = normalize_ymd(os.getenv("DATA_JOB_END_DATE"))
    trade_date = normalize_ymd(os.getenv("DATA_JOB_TRADE_DATE"))
    full_refresh = env_bool("DATA_JOB_FULL_REFRESH", default=False)

    if trade_date:
        return trade_date, trade_date, full_refresh

    if not end_date:
        end_date = latest_open_trade_date(cursor)

    if not start_date:
        cursor.execute(f"SELECT DATE_FORMAT(MAX(trade_date), '%Y%m%d') FROM {target_table}")
        max_trade_date = cursor.fetchone()[0]
        if max_trade_date:
            start_date = next_date_ymd(max_trade_date)
        else:
            start_date = end_date

    return start_date, end_date, full_refresh


def fetch_open_trade_dates(cursor, start_date: str, end_date: str) -> list[str]:
    if not start_date or not end_date or start_date > end_date:
        return []

    cursor.execute(
        """
        SELECT DATE_FORMAT(cal_date, '%%Y%%m%%d')
        FROM stock_trade_calendar
        WHERE is_open = 1
          AND cal_date >= STR_TO_DATE(%s, '%%Y%%m%%d')
          AND cal_date <= STR_TO_DATE(%s, '%%Y%%m%%d')
        ORDER BY cal_date
        """,
        (start_date, end_date),
    )
    return [row[0] for row in cursor.fetchall()]


def delete_trade_date_range(cursor, table_name: str, start_date: str, end_date: str) -> None:
    cursor.execute(
        f"""
        DELETE FROM {table_name}
        WHERE trade_date >= STR_TO_DATE(%s, '%%Y%%m%%d')
          AND trade_date <= STR_TO_DATE(%s, '%%Y%%m%%d')
        """,
        (start_date, end_date),
    )
