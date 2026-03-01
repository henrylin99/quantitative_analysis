import pandas as pd

from db_utils import DatabaseUtils
from job_env import fetch_open_trade_dates, resolve_date_window, delete_trade_date_range


def ensure_table(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS `stock_moneyflow_ths` (
          `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
          `trade_date` date NOT NULL COMMENT '交易日期',
          `name` varchar(50) DEFAULT NULL COMMENT '股票名称',
          `pct_change` decimal(10,2) DEFAULT NULL COMMENT '涨跌幅',
          `latest` decimal(10,2) DEFAULT NULL COMMENT '最新价',
          `net_amount` decimal(20,2) DEFAULT NULL COMMENT '净流入额',
          `net_d5_amount` decimal(20,2) DEFAULT NULL COMMENT '5日净流入额',
          `buy_lg_amount` decimal(20,2) DEFAULT NULL COMMENT '大单买入额',
          `buy_lg_amount_rate` decimal(10,2) DEFAULT NULL COMMENT '大单买入额占比',
          `buy_md_amount` decimal(20,2) DEFAULT NULL COMMENT '中单买入额',
          `buy_md_amount_rate` decimal(10,2) DEFAULT NULL COMMENT '中单买入额占比',
          `buy_sm_amount` decimal(20,2) DEFAULT NULL COMMENT '小单买入额',
          `buy_sm_amount_rate` decimal(10,2) DEFAULT NULL COMMENT '小单买入额占比',
          PRIMARY KEY (`ts_code`,`trade_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='同花顺个股资金流向数据表';
        '''
    )


def upsert(cursor, data):
    if data is None or data.empty:
        return 0

    numeric_columns = [col for col in data.columns if col not in ["ts_code", "trade_date", "name"]]
    for col in numeric_columns:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    for col in ["ts_code", "trade_date", "name"]:
        data[col] = data[col].replace({float("nan"): None, "nan": None})

    rows = [tuple(row[col] for col in data.columns) for _, row in data.iterrows()]

    cursor.executemany(
        '''
        INSERT INTO stock_moneyflow_ths (
            trade_date, ts_code, name, pct_change, latest, net_amount,
            net_d5_amount, buy_lg_amount, buy_lg_amount_rate, buy_md_amount,
            buy_md_amount_rate, buy_sm_amount, buy_sm_amount_rate
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            pct_change = VALUES(pct_change),
            latest = VALUES(latest),
            net_amount = VALUES(net_amount),
            net_d5_amount = VALUES(net_d5_amount),
            buy_lg_amount = VALUES(buy_lg_amount),
            buy_lg_amount_rate = VALUES(buy_lg_amount_rate),
            buy_md_amount = VALUES(buy_md_amount),
            buy_md_amount_rate = VALUES(buy_md_amount_rate),
            buy_sm_amount = VALUES(buy_sm_amount),
            buy_sm_amount_rate = VALUES(buy_sm_amount_rate)
        ''',
        rows,
    )
    return len(rows)


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        ensure_table(cursor)

        start_date, end_date, full_refresh = resolve_date_window(cursor, "stock_moneyflow_ths")
        trade_dates = fetch_open_trade_dates(cursor, start_date, end_date)
        if not trade_dates:
            print("[moneyflow_ths] 没有可执行的交易日，跳过。")
            return

        if full_refresh:
            delete_trade_date_range(cursor, "stock_moneyflow_ths", min(trade_dates), max(trade_dates))
            conn.commit()

        total_saved = 0
        for trade_date in trade_dates:
            data = pro.moneyflow_ths(trade_date=trade_date)
            saved = upsert(cursor, data)
            conn.commit()
            total_saved += saved
            print(f"[moneyflow_ths] trade_date={trade_date}, upsert={saved}")

        print(f"[moneyflow_ths] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
