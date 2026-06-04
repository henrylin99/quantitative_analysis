import baostock as bs
import pandas as pd

from parquet_job_helpers import get_stock_codes
from parquet_writer import save_partitioned_parquet


def _to_bs_code(ts_code: str) -> str:
    return ("sz." if ts_code.endswith(".SZ") else "sh.") + ts_code.split(".")[0]


def _fetch_minute(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    rs = bs.query_history_k_data_plus(
        stock_code,
        "date,time,code,open,high,low,close,volume,amount",
        start_date=start_date,
        end_date=end_date,
        frequency="15",
        adjustflag="2",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


def main():
    stock_list = get_stock_codes()
    if not stock_list:
        print("[min15] stock_basic.parquet is empty, skip.")
        return

    bs.login()
    try:
        frames = []
        for ts_code in stock_list:
            df = _fetch_minute(_to_bs_code(ts_code), "2025-03-01", "2025-05-29")
            if df is not None and not df.empty:
                df = df.rename(columns={"date": "trade_date", "code": "ts_code"})
                df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
                frames.append(df[["ts_code", "trade_date", "open", "high", "low", "close", "volume", "amount"]])

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            total_saved = save_partitioned_parquet(combined, "trade_date", "min15/daily")
            print(f"[min15] 完成，写入={total_saved}")
    finally:
        bs.logout()


if __name__ == "__main__":
    main()
