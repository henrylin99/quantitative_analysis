from db_utils import DatabaseUtils
from parquet_job_helpers import DailyFetchJob


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


class MoneyflowJob(DailyFetchJob):
    job_name = "moneyflow"
    rel_table = "moneyflow/daily"

    def fetch_one(self, trade_date):
        return self.api.moneyflow(trade_date=trade_date, fields=FIELDS)


def main():
    MoneyflowJob(api=DatabaseUtils.init_tushare_api()).run()


if __name__ == "__main__":
    main()
