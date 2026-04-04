import pandas as pd
import time

from db_utils import DatabaseUtils
from job_env import fetch_open_trade_dates, resolve_date_window, delete_trade_date_range


def ensure_table(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS `stock_cyq_perf` (
          `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
          `trade_date` date NOT NULL COMMENT '交易日期',
          `his_low` decimal(10,2) DEFAULT NULL COMMENT '历史最低价',
          `his_high` decimal(10,2) DEFAULT NULL COMMENT '历史最高价',
          `cost_5pct` decimal(10,2) DEFAULT NULL COMMENT '5%成本分位',
          `cost_15pct` decimal(10,2) DEFAULT NULL COMMENT '15%成本分位',
          `cost_50pct` decimal(10,2) DEFAULT NULL COMMENT '50%成本分位',
          `cost_85pct` decimal(10,2) DEFAULT NULL COMMENT '85%成本分位',
          `cost_95pct` decimal(10,2) DEFAULT NULL COMMENT '95%成本分位',
          `weight_avg` decimal(10,2) DEFAULT NULL COMMENT '加权平均成本',
          `winner_rate` decimal(10,2) DEFAULT NULL COMMENT '胜率',
          PRIMARY KEY (`ts_code`,`trade_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='每日筹码及胜率数据表';
        '''
    )


def upsert(cursor, data):
    if data is None or data.empty:
        return 0

    numeric_columns = [
        "his_low",
        "his_high",
        "cost_5pct",
        "cost_15pct",
        "cost_50pct",
        "cost_85pct",
        "cost_95pct",
        "weight_avg",
        "winner_rate",
    ]
    for col in numeric_columns:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    for col in ["ts_code", "trade_date"]:
        data[col] = data[col].replace({float("nan"): None, "nan": None})

    rows = [tuple(row[col] for col in data.columns) for _, row in data.iterrows()]
    cursor.executemany(
        '''
        INSERT INTO stock_cyq_perf (
            ts_code, trade_date, his_low, his_high, cost_5pct, cost_15pct,
            cost_50pct, cost_85pct, cost_95pct, weight_avg, winner_rate
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            his_low = VALUES(his_low),
            his_high = VALUES(his_high),
            cost_5pct = VALUES(cost_5pct),
            cost_15pct = VALUES(cost_15pct),
            cost_50pct = VALUES(cost_50pct),
            cost_85pct = VALUES(cost_85pct),
            cost_95pct = VALUES(cost_95pct),
            weight_avg = VALUES(weight_avg),
            winner_rate = VALUES(winner_rate)
        ''',
        rows,
    )
    return len(rows)


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        ensure_table(cursor)

        start_date, end_date, full_refresh = resolve_date_window(cursor, "stock_cyq_perf")
        trade_dates = fetch_open_trade_dates(cursor, start_date, end_date)
        if not trade_dates:
            print("[cyq_perf] 没有可执行的交易日，跳过。")
            return

        if full_refresh:
            delete_trade_date_range(cursor, "stock_cyq_perf", min(trade_dates), max(trade_dates))
            conn.commit()

        total_saved = 0
        for trade_date in trade_dates:
            print(f"正在获取 {trade_date} 的筹码及胜率数据...")
            data = pro.cyq_perf(
                trade_date=trade_date,
                fields=[
                    "ts_code",
                    "trade_date",
                    "his_low",
                    "his_high",
                    "cost_5pct",
                    "cost_15pct",
                    "cost_50pct",
                    "cost_85pct",
                    "cost_95pct",
                    "weight_avg",
                    "winner_rate",
                ],
            )
            saved = upsert(cursor, data)
            conn.commit()
            total_saved += saved
            print(f"成功处理 {trade_date} 的数据，共 {saved} 条记录")
            time.sleep(0.05)

        print(
            f"[cyq_perf] 完成，start={trade_dates[0]}, end={trade_dates[-1]}, "
            f"trade_days={len(trade_dates)}, total_upsert={total_saved}"
        )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
