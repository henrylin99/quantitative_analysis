from db_utils import DatabaseUtils
from parquet_job_helpers import DailyFetchJob


class DailyHistoryByDateJob(DailyFetchJob):
    job_name = "daily_history_by_date"
    rel_table = "daily_history/daily"

    def fetch_one(self, trade_date):
        return self.api.daily(trade_date=trade_date)


def main():
    DailyHistoryByDateJob(api=DatabaseUtils.init_tushare_api()).run()


if __name__ == "__main__":
    main()
