import pandas as pd
import time

from db_utils import DatabaseUtils
from job_env import fetch_open_trade_dates, resolve_date_window, delete_trade_date_range


def ensure_table(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS `stock_moneyflow` (
          `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
          `trade_date` date NOT NULL COMMENT '交易日期',
          `buy_sm_vol` decimal(20,2) DEFAULT NULL COMMENT '小单买入量（手）',
          `buy_sm_amount` decimal(20,2) DEFAULT NULL COMMENT '小单买入金额（万元）',
          `sell_sm_vol` decimal(20,2) DEFAULT NULL COMMENT '小单卖出量（手）',
          `sell_sm_amount` decimal(20,2) DEFAULT NULL COMMENT '小单卖出金额（万元）',
          `buy_md_vol` decimal(20,2) DEFAULT NULL COMMENT '中单买入量（手）',
          `buy_md_amount` decimal(20,2) DEFAULT NULL COMMENT '中单买入金额（万元）',
          `sell_md_vol` decimal(20,2) DEFAULT NULL COMMENT '中单卖出量（手）',
          `sell_md_amount` decimal(20,2) DEFAULT NULL COMMENT '中单卖出金额（万元）',
          `buy_lg_vol` decimal(20,2) DEFAULT NULL COMMENT '大单买入量（手）',
          `buy_lg_amount` decimal(20,2) DEFAULT NULL COMMENT '大单买入金额（万元）',
          `sell_lg_vol` decimal(20,2) DEFAULT NULL COMMENT '大单卖出量（手）',
          `sell_lg_amount` decimal(20,2) DEFAULT NULL COMMENT '大单卖出金额（万元）',
          `buy_elg_vol` decimal(20,2) DEFAULT NULL COMMENT '特大单买入量（手）',
          `buy_elg_amount` decimal(20,2) DEFAULT NULL COMMENT '特大单买入金额（万元）',
          `sell_elg_vol` decimal(20,2) DEFAULT NULL COMMENT '特大单卖出量（手）',
          `sell_elg_amount` decimal(20,2) DEFAULT NULL COMMENT '特大单卖出金额（万元）',
          `net_mf_vol` decimal(20,2) DEFAULT NULL COMMENT '净流入量（手）',
          `net_mf_amount` decimal(20,2) DEFAULT NULL COMMENT '净流入额（万元）',
          PRIMARY KEY (`ts_code`,`trade_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='个股资金流向数据表';
        '''
    )


def upsert(cursor, data):
    if data is None or data.empty:
        return 0

    numeric_columns = [col for col in data.columns if col not in ["ts_code", "trade_date"]]
    for col in numeric_columns:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    for col in ["ts_code", "trade_date"]:
        data[col] = data[col].replace({float("nan"): None, "nan": None})

    rows = [tuple(row[col] for col in data.columns) for _, row in data.iterrows()]

    cursor.executemany(
        '''
        INSERT INTO stock_moneyflow (
            ts_code, trade_date, buy_sm_vol, buy_sm_amount, sell_sm_vol,
            sell_sm_amount, buy_md_vol, buy_md_amount, sell_md_vol,
            sell_md_amount, buy_lg_vol, buy_lg_amount, sell_lg_vol,
            sell_lg_amount, buy_elg_vol, buy_elg_amount, sell_elg_vol,
            sell_elg_amount, net_mf_vol, net_mf_amount
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            buy_sm_vol = VALUES(buy_sm_vol),
            buy_sm_amount = VALUES(buy_sm_amount),
            sell_sm_vol = VALUES(sell_sm_vol),
            sell_sm_amount = VALUES(sell_sm_amount),
            buy_md_vol = VALUES(buy_md_vol),
            buy_md_amount = VALUES(buy_md_amount),
            sell_md_vol = VALUES(sell_md_vol),
            sell_md_amount = VALUES(sell_md_amount),
            buy_lg_vol = VALUES(buy_lg_vol),
            buy_lg_amount = VALUES(buy_lg_amount),
            sell_lg_vol = VALUES(sell_lg_vol),
            sell_lg_amount = VALUES(sell_lg_amount),
            buy_elg_vol = VALUES(buy_elg_vol),
            buy_elg_amount = VALUES(buy_elg_amount),
            sell_elg_vol = VALUES(sell_elg_vol),
            sell_elg_amount = VALUES(sell_elg_amount),
            net_mf_vol = VALUES(net_mf_vol),
            net_mf_amount = VALUES(net_mf_amount)
        ''',
        rows,
    )
    return len(rows)


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        ensure_table(cursor)

        start_date, end_date, full_refresh = resolve_date_window(cursor, "stock_moneyflow")
        trade_dates = fetch_open_trade_dates(cursor, start_date, end_date)
        if not trade_dates:
            print("[moneyflow] 没有可执行的交易日，跳过。")
            return

        if full_refresh:
            delete_trade_date_range(cursor, "stock_moneyflow", min(trade_dates), max(trade_dates))
            conn.commit()

        total_saved = 0
        for trade_date in trade_dates:
            print(f"[moneyflow] trade_date={trade_date}")
            data = pro.moneyflow(trade_date=trade_date)
            saved = upsert(cursor, data)
            conn.commit()
            total_saved += saved
            time.sleep(0.05)

        print(f"[moneyflow] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
