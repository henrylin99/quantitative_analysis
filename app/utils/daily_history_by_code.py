from db_utils import DatabaseUtils
from parquet_job_helpers import get_stock_codes, resolve_trade_dates
from parquet_writer import save_partitioned_parquet
from stock_partition import auto_rebuild_stock_partition


def main():
    pro = DatabaseUtils.init_tushare_api()
    stock_list = get_stock_codes()
    trade_dates, _ = resolve_trade_dates()

    total_saved = 0
    saved_dates = []
    for trade_date in trade_dates:
        frames = []
        for ts_code in stock_list:
            df = pro.daily(ts_code=ts_code, trade_date=trade_date)
            if df is not None and not df.empty:
                frames.append(df)
        if frames:
            import pandas as pd

            saved = save_partitioned_parquet(
                pd.concat(frames, ignore_index=True), "trade_date", "daily_history/daily"
            )
            total_saved += saved
            if saved > 0:
                saved_dates.append(trade_date)
        print(f"[daily_history_by_code] trade_date={trade_date}")

    print(
        f"[daily_history_by_code] 完成，trade_days={len(trade_dates)}, total_upsert={total_saved}"
    )

    # 落盘成功后增量合并股票分区（个股查询快路径），失败不影响本作业
    if saved_dates:
        auto_rebuild_stock_partition("daily_history/daily", saved_dates)


if __name__ == "__main__":
    main()
