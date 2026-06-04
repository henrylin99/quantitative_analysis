from db_utils import DatabaseUtils
from parquet_writer import save_single_parquet


def main():
    pro = DatabaseUtils.init_tushare_api()
    data = pro.trade_cal(
        exchange="",
        start_date="20240101",
        end_date="20261231",
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    save_single_parquet(data, "stock_trade_calendar.parquet")


if __name__ == "__main__":
    main()
