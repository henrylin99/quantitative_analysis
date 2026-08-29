from db_utils import DatabaseUtils
from parquet_job_helpers import DailyFetchJob


FIELDS = [
    "ts_code",
    "trade_date",
    "close",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
]


class DailyBasicJob(DailyFetchJob):
    job_name = "daily_basic"
    rel_table = "daily_basic/daily"

    def fetch_one(self, trade_date):
        return self.api.daily_basic(trade_date=trade_date, fields=FIELDS)


def main():
    DailyBasicJob(api=DatabaseUtils.init_tushare_api()).run()


if __name__ == "__main__":
    main()
