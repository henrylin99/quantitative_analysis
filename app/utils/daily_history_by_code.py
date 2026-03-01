import pandas as pd

from db_utils import DatabaseUtils
from job_env import resolve_date_window, delete_trade_date_range


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


def upsert_batch(cursor, rows):
    if not rows:
        return

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


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        ensure_table(cursor)

        start_date, end_date, full_refresh = resolve_date_window(cursor, "stock_daily_history")
        if not start_date or not end_date or start_date > end_date:
            print("[daily_history_by_code] 没有可执行的日期区间，跳过。")
            return

        if full_refresh:
            delete_trade_date_range(cursor, "stock_daily_history", start_date, end_date)
            conn.commit()

        cursor.execute("SELECT ts_code FROM stock_basic")
        stock_list = [row[0] for row in cursor.fetchall()]

        total_saved = 0
        batch_size = 50
        for i in range(0, len(stock_list), batch_size):
            batch = stock_list[i:i + batch_size]
            rows = []
            for ts_code in batch:
                df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is None or df.empty:
                    continue
                df = df.replace({pd.NA: None, float("nan"): None})
                rows.extend(
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
                )

            upsert_batch(cursor, rows)
            conn.commit()
            total_saved += len(rows)
            print(f"[daily_history_by_code] batch={i // batch_size + 1}, upsert={len(rows)}")

        print(
            f"[daily_history_by_code] 完成，start={start_date}, end={end_date}, "
            f"total_upsert={total_saved}"
        )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
