import pandas as pd
import time

from db_utils import DatabaseUtils
from job_env import fetch_open_trade_dates, resolve_date_window, delete_trade_date_range


def ensure_table(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS `stock_factor` (
          `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
          `trade_date` date NOT NULL COMMENT '交易日期',
          `close` decimal(10,2) DEFAULT NULL COMMENT '收盘价',
          `open` decimal(10,2) DEFAULT NULL COMMENT '开盘价',
          `high` decimal(10,2) DEFAULT NULL COMMENT '最高价',
          `low` decimal(10,2) DEFAULT NULL COMMENT '最低价',
          `pre_close` decimal(10,2) DEFAULT NULL COMMENT '昨收价',
          `change` decimal(10,2) DEFAULT NULL COMMENT '涨跌额',
          `pct_change` decimal(10,2) DEFAULT NULL COMMENT '涨跌幅',
          `vol` decimal(20,2) DEFAULT NULL COMMENT '成交量',
          `amount` decimal(20,2) DEFAULT NULL COMMENT '成交额',
          `adj_factor` decimal(10,2) DEFAULT NULL COMMENT '复权因子',
          `open_hfq` decimal(10,2) DEFAULT NULL COMMENT '后复权开盘价',
          `open_qfq` decimal(10,2) DEFAULT NULL COMMENT '前复权开盘价',
          `close_hfq` decimal(10,2) DEFAULT NULL COMMENT '后复权收盘价',
          `close_qfq` decimal(10,2) DEFAULT NULL COMMENT '前复权收盘价',
          `high_hfq` decimal(10,2) DEFAULT NULL COMMENT '后复权最高价',
          `high_qfq` decimal(10,2) DEFAULT NULL COMMENT '前复权最高价',
          `low_hfq` decimal(10,2) DEFAULT NULL COMMENT '后复权最低价',
          `low_qfq` decimal(10,2) DEFAULT NULL COMMENT '前复权最低价',
          `pre_close_hfq` decimal(10,2) DEFAULT NULL COMMENT '后复权昨收价',
          `pre_close_qfq` decimal(10,2) DEFAULT NULL COMMENT '前复权昨收价',
          `macd_dif` decimal(10,2) DEFAULT NULL COMMENT 'MACD DIF值',
          `macd_dea` decimal(10,2) DEFAULT NULL COMMENT 'MACD DEA值',
          `macd` decimal(10,2) DEFAULT NULL COMMENT 'MACD值',
          `kdj_k` decimal(10,2) DEFAULT NULL COMMENT 'KDJ K值',
          `kdj_d` decimal(10,2) DEFAULT NULL COMMENT 'KDJ D值',
          `kdj_j` decimal(10,2) DEFAULT NULL COMMENT 'KDJ J值',
          `rsi_6` decimal(10,2) DEFAULT NULL COMMENT 'RSI 6日',
          `rsi_12` decimal(10,2) DEFAULT NULL COMMENT 'RSI 12日',
          `rsi_24` decimal(10,2) DEFAULT NULL COMMENT 'RSI 24日',
          `boll_upper` decimal(10,2) DEFAULT NULL COMMENT '布林上轨',
          `boll_mid` decimal(10,2) DEFAULT NULL COMMENT '布林中轨',
          `boll_lower` decimal(10,2) DEFAULT NULL COMMENT '布林下轨',
          `cci` decimal(10,2) DEFAULT NULL COMMENT 'CCI指标',
          PRIMARY KEY (`ts_code`,`trade_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票技术面因子数据表';
        '''
    )


def upsert(cursor, data):
    if data is None or data.empty:
        return 0

    numeric_columns = [
        "close",
        "open",
        "high",
        "low",
        "pre_close",
        "change",
        "pct_change",
        "vol",
        "amount",
        "adj_factor",
        "open_hfq",
        "open_qfq",
        "close_hfq",
        "close_qfq",
        "high_hfq",
        "high_qfq",
        "low_hfq",
        "low_qfq",
        "pre_close_hfq",
        "pre_close_qfq",
        "macd_dif",
        "macd_dea",
        "macd",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "rsi_6",
        "rsi_12",
        "rsi_24",
        "boll_upper",
        "boll_mid",
        "boll_lower",
        "cci",
    ]
    for col in numeric_columns:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    for col in ["ts_code", "trade_date"]:
        data[col] = data[col].replace({float("nan"): None, "nan": None})

    rows = [tuple(row[col] for col in data.columns) for _, row in data.iterrows()]
    cursor.executemany(
        '''
        INSERT INTO stock_factor (
            ts_code, trade_date, close, open, high, low, pre_close, `change`,
            pct_change, vol, amount, adj_factor, open_hfq, open_qfq, close_hfq,
            close_qfq, high_hfq, high_qfq, low_hfq, low_qfq, pre_close_hfq,
            pre_close_qfq, macd_dif, macd_dea, macd, kdj_k, kdj_d, kdj_j,
            rsi_6, rsi_12, rsi_24, boll_upper, boll_mid, boll_lower, cci
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            close = VALUES(close),
            open = VALUES(open),
            high = VALUES(high),
            low = VALUES(low),
            pre_close = VALUES(pre_close),
            `change` = VALUES(`change`),
            pct_change = VALUES(pct_change),
            vol = VALUES(vol),
            amount = VALUES(amount),
            adj_factor = VALUES(adj_factor),
            open_hfq = VALUES(open_hfq),
            open_qfq = VALUES(open_qfq),
            close_hfq = VALUES(close_hfq),
            close_qfq = VALUES(close_qfq),
            high_hfq = VALUES(high_hfq),
            high_qfq = VALUES(high_qfq),
            low_hfq = VALUES(low_hfq),
            low_qfq = VALUES(low_qfq),
            pre_close_hfq = VALUES(pre_close_hfq),
            pre_close_qfq = VALUES(pre_close_qfq),
            macd_dif = VALUES(macd_dif),
            macd_dea = VALUES(macd_dea),
            macd = VALUES(macd),
            kdj_k = VALUES(kdj_k),
            kdj_d = VALUES(kdj_d),
            kdj_j = VALUES(kdj_j),
            rsi_6 = VALUES(rsi_6),
            rsi_12 = VALUES(rsi_12),
            rsi_24 = VALUES(rsi_24),
            boll_upper = VALUES(boll_upper),
            boll_mid = VALUES(boll_mid),
            boll_lower = VALUES(boll_lower),
            cci = VALUES(cci)
        ''',
        rows,
    )
    return len(rows)


def main():
    pro = DatabaseUtils.init_tushare_api()
    conn, cursor = DatabaseUtils.connect_to_mysql()

    try:
        ensure_table(cursor)

        start_date, end_date, full_refresh = resolve_date_window(cursor, "stock_factor")
        trade_dates = fetch_open_trade_dates(cursor, start_date, end_date)
        if not trade_dates:
            print("[stk_factor] 没有可执行的交易日，跳过。")
            return

        if full_refresh:
            delete_trade_date_range(cursor, "stock_factor", min(trade_dates), max(trade_dates))
            conn.commit()

        total_saved = 0
        for trade_date in trade_dates:
            print(f"[stk_factor] trade_date={trade_date}")
            data = pro.stk_factor(
                trade_date=trade_date,
                fields=[
                    "ts_code",
                    "trade_date",
                    "close",
                    "open",
                    "high",
                    "low",
                    "pre_close",
                    "change",
                    "pct_change",
                    "vol",
                    "amount",
                    "adj_factor",
                    "open_hfq",
                    "open_qfq",
                    "close_hfq",
                    "close_qfq",
                    "high_hfq",
                    "high_qfq",
                    "low_hfq",
                    "low_qfq",
                    "pre_close_hfq",
                    "pre_close_qfq",
                    "macd_dif",
                    "macd_dea",
                    "macd",
                    "kdj_k",
                    "kdj_d",
                    "kdj_j",
                    "rsi_6",
                    "rsi_12",
                    "rsi_24",
                    "boll_upper",
                    "boll_mid",
                    "boll_lower",
                    "cci",
                ],
            )
            saved = upsert(cursor, data)
            conn.commit()
            total_saved += saved
            print(f"[stk_factor] 完成 {trade_date}，upsert={saved}")
            time.sleep(1)

        print(
            f"[stk_factor] 完成，start={trade_dates[0]}, end={trade_dates[-1]}, "
            f"trade_days={len(trade_dates)}, total_upsert={total_saved}"
        )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
