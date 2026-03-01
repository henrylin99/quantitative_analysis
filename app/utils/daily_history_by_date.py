import pandas as pd

from db_utils import DatabaseUtils
from job_env import fetch_open_trade_dates, resolve_date_window, delete_trade_date_range


def ensure_table(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS `stock_daily_history` (
          `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
          `trade_date` date NOT NULL COMMENT '交易日期',
          `open` decimal(10,4) DEFAULT NULL COMMENT '开盘价',
          `high` decimal(10,4) DEFAULT NULL COMMENT '最高价',
          `low` decimal(10,4) DEFAULT NULL COMMENT '最低价',
          `close` decimal(10,4) DEFAULT NULL COMMENT '收盘价',
          `pre_close` decimal(10,4) DEFAULT NULL COMMENT '昨收价【除权价，前复权】',
          `change_c` decimal(10,4) DEFAULT NULL COMMENT '涨跌额',
          `pct_chg` decimal(10,4) DEFAULT NULL COMMENT '涨跌幅',
          `vol` bigint DEFAULT NULL COMMENT '成交量（手）',
          `amount` decimal(20,4) DEFAULT NULL COMMENT '成交额（千元）',
          PRIMARY KEY (`ts_code`,`trade_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票日线行情数据表';
        '''
    )


def upsert_trade_date(cursor, df):
    if df is None or df.empty:
        return 0

    df = df.replace({pd.NA: None, float("nan"): None})
    rows = [
        (
            row["ts_code"],
            row["trade_date"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["pre_close"],
            row["change"],
            row["pct_chg"],
            row["vol"],
            row["amount"],
        )
        for _, row in df.iterrows()
    ]

    cursor.executemany(
        '''
        INSERT INTO stock_daily_history (
            ts_code, trade_date, open, high, low, close, pre_close, change_c, pct_chg, vol, amount
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open = VALUES(open),
            high = VALUES(high),
            low = VALUES(low),
            close = VALUES(close),
            pre_close = VALUES(pre_close),
            change_c = VALUES(change_c),
            pct_chg = VALUES(pct_chg),
            vol = VALUES(vol),
            amount = VALUES(amount)
        ''',
        rows,
    )
    return len(rows)


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        ensure_table(cursor)

        start_date, end_date, full_refresh = resolve_date_window(cursor, "stock_daily_history")
        trade_dates = fetch_open_trade_dates(cursor, start_date, end_date)
        if not trade_dates:
            print("[daily_history_by_date] 没有可执行的交易日，跳过。")
            return

        if full_refresh:
            delete_trade_date_range(cursor, "stock_daily_history", min(trade_dates), max(trade_dates))
            conn.commit()

        total_saved = 0
        for trade_date in trade_dates:
            df = pro.daily(trade_date=trade_date)
            saved = upsert_trade_date(cursor, df)
            conn.commit()
            total_saved += saved
            print(f"[daily_history_by_date] trade_date={trade_date}, upsert={saved}")

        print(
            f"[daily_history_by_date] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}"
        )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
