from db_utils import DatabaseUtils
from parquet_job_helpers import resolve_trade_dates
from parquet_writer import save_partitioned_parquet


FIELDS = [
    "ts_code",
    "trade_date",
    "name",
    "pct_change",
    "latest",
    "net_amount",
    "net_d5_amount",
    "buy_lg_amount",
    "buy_lg_amount_rate",
    "buy_md_amount",
    "buy_md_amount_rate",
    "buy_sm_amount",
    "buy_sm_amount_rate",
]


def main():
    pro = DatabaseUtils.init_tushare_api()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    for trade_date in trade_dates:
        data = pro.moneyflow_ths(trade_date=trade_date, fields=FIELDS)
        total_saved += save_partitioned_parquet(data, "trade_date", "moneyflow_ths/daily")
        print(f"[moneyflow_ths] trade_date={trade_date}, upsert={len(data) if data is not None else 0}")

    print(f"[moneyflow_ths] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}")


if __name__ == "__main__":
    main()
