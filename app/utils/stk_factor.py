import time

from db_utils import DatabaseUtils
from parquet_job_helpers import resolve_trade_dates
from parquet_writer import save_partitioned_parquet


FIELDS = [
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
]


def main():
    pro = DatabaseUtils.init_tushare_api()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    for trade_date in trade_dates:
        print(f"[stk_factor] trade_date={trade_date}")
        data = pro.stk_factor(trade_date=trade_date, fields=FIELDS)
        total_saved += save_partitioned_parquet(data, "trade_date", "stk_factor/daily")
        print(f"[stk_factor] 完成 {trade_date}，upsert={len(data) if data is not None else 0}")
        time.sleep(0.1)

    print(
        f"[stk_factor] 完成，start={trade_dates[0] if trade_dates else None}, "
        f"end={trade_dates[-1] if trade_dates else None}, trade_days={len(trade_dates)}, "
        f"total_upsert={total_saved}"
    )


if __name__ == "__main__":
    main()
