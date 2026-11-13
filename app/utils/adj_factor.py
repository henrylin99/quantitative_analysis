from db_utils import DatabaseUtils
from parquet_job_helpers import DailyFetchJob


class AdjFactorJob(DailyFetchJob):
    """复权因子（独立表，data/adj_factor/daily）。

    此前 adj_factor 藏在已停更的 stk_factor 作业字段里，从零初始化后
    无任何作业生产本表——get_return_prices/backtest_engine 的复权链
    会静默退化为不复权。此作业按交易日拉全市场复权因子补上该缺口。
    """

    job_name = "adj_factor"
    rel_table = "adj_factor/daily"

    def fetch_one(self, trade_date):
        return self.api.adj_factor(trade_date=trade_date)


def main():
    AdjFactorJob(api=DatabaseUtils.init_tushare_api()).run()


if __name__ == "__main__":
    main()
