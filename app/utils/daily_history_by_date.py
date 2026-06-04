from db_utils import DatabaseUtils
from parquet_job_helpers import resolve_trade_dates
from parquet_writer import save_partitioned_parquet


def main():
    pro = DatabaseUtils.init_tushare_api()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    for trade_date in trade_dates:
        df = pro.daily(trade_date=trade_date)
        total_saved += save_partitioned_parquet(df, "trade_date", "daily_history/daily")
        print(f"[daily_history_by_date] trade_date={trade_date}")

    print(
        f"[daily_history_by_date] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}"
    )


if __name__ == "__main__":
    main()
