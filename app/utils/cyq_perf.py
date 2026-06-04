import time

from db_utils import DatabaseUtils
from parquet_job_helpers import resolve_trade_dates
from parquet_writer import save_partitioned_parquet


FIELDS = [
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
]


def main():
    pro = DatabaseUtils.init_tushare_api()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    for trade_date in trade_dates:
        print(f"正在获取 {trade_date} 的筹码及胜率数据...")
        data = pro.cyq_perf(trade_date=trade_date, fields=FIELDS)
        total_saved += save_partitioned_parquet(data, "trade_date", "cyq_perf/daily")
        print(f"成功处理 {trade_date} 的数据，共 {len(data) if data is not None else 0} 条记录")
        time.sleep(0.1)

    print(f"[cyq_perf] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}")


if __name__ == "__main__":
    main()
