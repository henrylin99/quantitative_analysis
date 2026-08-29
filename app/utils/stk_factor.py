from db_utils import DatabaseUtils
from parquet_job_helpers import DailyFetchJob


FIELDS = [
    "ts_code",
    "trade_date",
    "close",
    "open",
    "high",
    "low",
    "pre_close",
    "change",
    "pct_change",
    "vol",
    "amount",
    "adj_factor",
    "open_hfq",
    "open_qfq",
    "close_hfq",
    "close_qfq",
    "high_hfq",
    "high_qfq",
    "low_hfq",
    "low_qfq",
    "pre_close_hfq",
    "pre_close_qfq",
    "macd_dif",
    "macd_dea",
    "macd",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "rsi_6",
    "rsi_12",
    "rsi_24",
    "boll_upper",
    "boll_mid",
    "boll_lower",
    "cci",
]


class StkFactorJob(DailyFetchJob):
    job_name = "stk_factor"
    rel_table = "stk_factor/daily"

    def fetch_one(self, trade_date):
        return self.api.stk_factor(trade_date=trade_date, fields=FIELDS)


def main():
    StkFactorJob(api=DatabaseUtils.init_tushare_api()).run()


if __name__ == "__main__":
    main()
