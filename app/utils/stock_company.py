from db_utils import DatabaseUtils
from parquet_writer import save_single_parquet


def main():
    pro = DatabaseUtils.init_tushare_api()
    data = pro.stock_company(
        exchange="SSE",
        fields="ts_code,exchange,chairman,manager,secretary,reg_capital,setup_date,province",
    )
    save_single_parquet(data, "stock_company.parquet")


if __name__ == "__main__":
    main()
