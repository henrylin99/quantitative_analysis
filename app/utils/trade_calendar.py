from db_utils import DatabaseUtils
from parquet_writer import save_single_parquet


def main():
    pro = DatabaseUtils.init_tushare_api()
    # 从 2005 年起覆盖完整历史：财务因子公告日对齐交易日需要历史日历，
    # 只下载近年会让早期快照落在周末且无法对齐，精确匹配永远查不到
    data = pro.trade_cal(
        exchange="",
        start_date="20050101",
        end_date="20261231",
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    save_single_parquet(data, "stock_trade_calendar.parquet")


if __name__ == "__main__":
    main()
