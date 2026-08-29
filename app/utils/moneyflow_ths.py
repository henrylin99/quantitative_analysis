from db_utils import DatabaseUtils
from parquet_job_helpers import DailyFetchJob


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


class MoneyflowThsJob(DailyFetchJob):
    job_name = "moneyflow_ths"
    rel_table = "moneyflow_ths/daily"

    def fetch_one(self, trade_date):
        return self.api.moneyflow_ths(trade_date=trade_date, fields=FIELDS)


def main():
    MoneyflowThsJob(api=DatabaseUtils.init_tushare_api()).run()


if __name__ == "__main__":
    main()
