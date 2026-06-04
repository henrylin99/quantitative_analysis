from db_utils import DatabaseUtils
from parquet_writer import save_single_parquet


def main():
    pro = DatabaseUtils.init_tushare_api()
    data = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,list_date",
    )
    save_single_parquet(data, "stock_basic.parquet")


if __name__ == "__main__":
    main()
