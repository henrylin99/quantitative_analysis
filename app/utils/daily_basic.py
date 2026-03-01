import os
from datetime import datetime, timedelta

import pandas as pd

from db_utils import DatabaseUtils

FIELDS = [
    "ts_code",
    "trade_date",
    "close",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
]


def _normalize_ymd(date_str: str | None) -> str | None:
    if not date_str:
        return None
    text = str(date_str).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return text
    return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")


def _to_bool(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_dates(cursor) -> tuple[list[str], bool]:
    start_date = _normalize_ymd(os.getenv("DATA_JOB_START_DATE"))
    end_date = _normalize_ymd(os.getenv("DATA_JOB_END_DATE"))
    trade_date = _normalize_ymd(os.getenv("DATA_JOB_TRADE_DATE"))
    full_refresh = _to_bool(os.getenv("DATA_JOB_FULL_REFRESH"))

    if trade_date:
        return [trade_date], full_refresh

    if not end_date:
        cursor.execute(
            """
            SELECT DATE_FORMAT(MAX(cal_date), '%Y%m%d')
            FROM stock_trade_calendar
            WHERE is_open = 1 AND cal_date <= CURDATE()
            """
        )
        end_date = cursor.fetchone()[0]

    if not start_date:
        cursor.execute("SELECT DATE_FORMAT(MAX(trade_date), '%Y%m%d') FROM stock_daily_basic")
        max_trade_date = cursor.fetchone()[0]
        if max_trade_date:
            next_day = datetime.strptime(max_trade_date, "%Y%m%d") + timedelta(days=1)
            start_date = next_day.strftime("%Y%m%d")
        else:
            start_date = end_date

    if not start_date or not end_date or start_date > end_date:
        return [], full_refresh

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
    return [row[0] for row in cursor.fetchall()], full_refresh


def _ensure_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_daily_basic (
          ts_code varchar(20) NOT NULL COMMENT 'TS股票代码',
          trade_date date NOT NULL COMMENT '交易日期',
          close decimal(10,2) DEFAULT NULL COMMENT '当日收盘价',
          turnover_rate decimal(10,2) DEFAULT NULL COMMENT '换手率（%）',
          turnover_rate_f decimal(10,2) DEFAULT NULL COMMENT '换手率（自由流通股）',
          volume_ratio decimal(10,2) DEFAULT NULL COMMENT '量比',
          pe decimal(10,2) DEFAULT NULL COMMENT '市盈率（总市值/净利润， 亏损的PE为空）',
          pe_ttm decimal(10,2) DEFAULT NULL COMMENT '市盈率（TTM，亏损的PE为空）',
          pb decimal(10,2) DEFAULT NULL COMMENT '市净率（总市值/净资产）',
          ps decimal(10,2) DEFAULT NULL COMMENT '市销率',
          ps_ttm decimal(10,2) DEFAULT NULL COMMENT '市销率（TTM）',
          dv_ratio decimal(10,2) DEFAULT NULL COMMENT '股息率 （%）',
          dv_ttm decimal(10,2) DEFAULT NULL COMMENT '股息率（TTM）（%）',
          total_share decimal(20,2) DEFAULT NULL COMMENT '总股本 （万股）',
          float_share decimal(20,2) DEFAULT NULL COMMENT '流通股本 （万股）',
          free_share decimal(20,2) DEFAULT NULL COMMENT '自由流通股本 （万）',
          total_mv decimal(20,2) DEFAULT NULL COMMENT '总市值 （万元）',
          circ_mv decimal(20,2) DEFAULT NULL COMMENT '流通市值（万元）',
          PRIMARY KEY (ts_code,trade_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票日线基本数据表';
        """
    )


def _delete_for_refresh(cursor, dates: list[str], full_refresh: bool):
    if not full_refresh or not dates:
        return

    min_date = min(dates)
    max_date = max(dates)
    cursor.execute(
        """
        DELETE FROM stock_daily_basic
        WHERE trade_date >= STR_TO_DATE(%s, '%%Y%%m%%d')
          AND trade_date <= STR_TO_DATE(%s, '%%Y%%m%%d')
        """,
        (min_date, max_date),
    )


def _save_trade_date(cursor, conn, df: pd.DataFrame):
    if df.empty:
        return 0

    df = df.replace({pd.NA: None, float("nan"): None})
    insert_data = [tuple(row) for row in df[FIELDS].values]
    cursor.executemany(
        """
        INSERT INTO stock_daily_basic (
            ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe,
            pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, total_share, float_share,
            free_share, total_mv, circ_mv
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            close = VALUES(close),
            turnover_rate = VALUES(turnover_rate),
            turnover_rate_f = VALUES(turnover_rate_f),
            volume_ratio = VALUES(volume_ratio),
            pe = VALUES(pe),
            pe_ttm = VALUES(pe_ttm),
            pb = VALUES(pb),
            ps = VALUES(ps),
            ps_ttm = VALUES(ps_ttm),
            dv_ratio = VALUES(dv_ratio),
            dv_ttm = VALUES(dv_ttm),
            total_share = VALUES(total_share),
            float_share = VALUES(float_share),
            free_share = VALUES(free_share),
            total_mv = VALUES(total_mv),
            circ_mv = VALUES(circ_mv)
        """,
        insert_data,
    )
    conn.commit()
    return len(insert_data)


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        _ensure_table(cursor)
        trade_dates, full_refresh = _resolve_dates(cursor)

        if not trade_dates:
            print("[daily_basic] 没有可执行的交易日，跳过。")
            return

        _delete_for_refresh(cursor, trade_dates, full_refresh)
        conn.commit()

        total_saved = 0
        for trade_date in trade_dates:
            print(f"[daily_basic] 拉取 {trade_date}")
            df = pro.daily_basic(trade_date=trade_date, fields=FIELDS)
            saved = _save_trade_date(cursor, conn, df)
            total_saved += saved

        print(f"[daily_basic] 完成，处理交易日={len(trade_dates)}，写入/更新记录={total_saved}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
