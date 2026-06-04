from db_utils import DatabaseUtils
from parquet_job_helpers import resolve_trade_dates
from parquet_writer import save_partitioned_parquet


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


def main():
    pro = DatabaseUtils.init_tushare_api()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    for trade_date in trade_dates:
        print(f"[daily_basic] 拉取 {trade_date}")
        df = pro.daily_basic(trade_date=trade_date, fields=FIELDS)
        total_saved += save_partitioned_parquet(df, "trade_date", "daily_basic/daily")

    print(f"[daily_basic] 完成，处理交易日={len(trade_dates)}，写入/更新记录={total_saved}")


if __name__ == "__main__":
    main()
