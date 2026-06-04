import time

from db_utils import DatabaseUtils
from parquet_job_helpers import resolve_trade_dates
from parquet_writer import save_partitioned_parquet


FIELDS = [
    "ts_code",
    "trade_date",
    "buy_sm_vol",
    "buy_sm_amount",
    "sell_sm_vol",
    "sell_sm_amount",
    "buy_md_vol",
    "buy_md_amount",
    "sell_md_vol",
    "sell_md_amount",
    "buy_lg_vol",
    "buy_lg_amount",
    "sell_lg_vol",
    "sell_lg_amount",
    "buy_elg_vol",
    "buy_elg_amount",
    "sell_elg_vol",
    "sell_elg_amount",
    "net_mf_vol",
    "net_mf_amount",
]


def main():
    pro = DatabaseUtils.init_tushare_api()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    for trade_date in trade_dates:
        print(f"[moneyflow] trade_date={trade_date}")
        data = pro.moneyflow(trade_date=trade_date, fields=FIELDS)
        total_saved += save_partitioned_parquet(data, "trade_date", "moneyflow/daily")
        time.sleep(0.05)

    print(f"[moneyflow] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}")


if __name__ == "__main__":
    main()
