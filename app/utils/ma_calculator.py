import numpy as np
import pandas as pd

from app.services.data_reader import ParquetDataReader
from parquet_job_helpers import get_stock_codes
from parquet_writer import save_single_parquet


def calculate_ema_manually(prices, period):
    if len(prices) < period:
        return None

    sma = np.mean(prices[:period])
    ema_values = [sma]
    multiplier = 2 / (period + 1)

    for i in range(period, len(prices)):
        ema = (prices[i] * multiplier) + (ema_values[-1] * (1 - multiplier))
        ema_values.append(ema)

    return ema_values[-1]


def main():
    reader = ParquetDataReader()
    stock_codes = get_stock_codes()
    rows = []

    for ts_code in stock_codes:
        df = reader.get_daily(ts_codes=[ts_code])
        if df.empty:
            continue

        df = df.sort_values("trade_date").tail(250).copy()
        if len(df) < 5:
            continue
        df["close"] = pd.to_numeric(df["close"], errors="coerce")

        ma5 = df["close"].rolling(window=5).mean().iloc[-1] if len(df) >= 5 else None
        ma10 = df["close"].rolling(window=10).mean().iloc[-1] if len(df) >= 10 else None
        ma20 = df["close"].rolling(window=20).mean().iloc[-1] if len(df) >= 20 else None
        ma30 = df["close"].rolling(window=30).mean().iloc[-1] if len(df) >= 30 else None
        ma60 = df["close"].rolling(window=60).mean().iloc[-1] if len(df) >= 60 else None
        ma120 = df["close"].rolling(window=120).mean().iloc[-1] if len(df) >= 120 else None

        close_values = df["close"].values
        ema5 = df["close"].ewm(span=5, adjust=False).mean().iloc[-1] if len(df) >= 5 else None
        ema10 = df["close"].ewm(span=10, adjust=False).mean().iloc[-1] if len(df) >= 10 else None
        ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1] if len(df) >= 20 else None
        ema30 = df["close"].ewm(span=30, adjust=False).mean().iloc[-1] if len(df) >= 30 else None
        ema60 = calculate_ema_manually(close_values, 60) if len(df) >= 60 else None
        ema120 = calculate_ema_manually(close_values, 120) if len(df) >= 120 else None

        rows.append(
            {
                "ts_code": ts_code,
                "ma5": float(ma5) if ma5 is not None else None,
                "ma10": float(ma10) if ma10 is not None else None,
                "ma20": float(ma20) if ma20 is not None else None,
                "ma30": float(ma30) if ma30 is not None else None,
                "ma60": float(ma60) if ma60 is not None else None,
                "ma120": float(ma120) if ma120 is not None else None,
                "ema5": float(ema5) if ema5 is not None else None,
                "ema10": float(ema10) if ema10 is not None else None,
                "ema20": float(ema20) if ema20 is not None else None,
                "ema30": float(ema30) if ema30 is not None else None,
                "ema60": float(ema60) if ema60 is not None else None,
                "ema120": float(ema120) if ema120 is not None else None,
            }
        )

    if rows:
        save_single_parquet(pd.DataFrame(rows), "stock_ma_data.parquet")
        print("MA和EMA计算完成!")


if __name__ == "__main__":
    main()
