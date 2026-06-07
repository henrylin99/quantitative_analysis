"""
大宽表构建脚本
从 daily_basic、stk_factor、moneyflow、stock_basic 合并最新交易日数据，
输出 stock_business.parquet（仅保留最新一天）。

Usage:
    python app/utils/wide_table_builder.py

Registered as a derived job in DataJobService.
"""

import sys
import os

# 支持两种运行方式：
# 1. 作为 data_jobs 子进程（PYTHONPATH 已含项目根目录）
# 2. 从 Flask app context 直接 import
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd

from app.services.data_reader import ParquetDataReader
from app.utils.parquet_writer import save_single_parquet


# stk_factor 列 → 宽表列名映射
STK_FACTOR_RENAME = {
    "open": "factor_open",
    "high": "factor_high",
    "low": "factor_low",
    "pre_close": "factor_pre_close",
    "change": "factor_change",
    "pct_change": "factor_pct_change",
    "vol": "factor_vol",
    "amount": "factor_amount",
    "macd_dif": "factor_macd_dif",
    "macd_dea": "factor_macd_dea",
    "macd": "factor_macd",
    "kdj_k": "factor_kdj_k",
    "kdj_d": "factor_kdj_d",
    "kdj_j": "factor_kdj_j",
    "rsi_6": "factor_rsi_6",
    "rsi_12": "factor_rsi_12",
    "rsi_24": "factor_rsi_24",
    "boll_upper": "factor_boll_upper",
    "boll_mid": "factor_boll_mid",
    "boll_lower": "factor_boll_lower",
    "cci": "factor_cci",
}

# stk_factor 中需要保留但不改名的列
STK_FACTOR_KEEP = ["ts_code", "adj_factor"]

# stk_factor 中需要丢弃的列（与 daily_basic 重复 或 不需要）
STK_FACTOR_DROP = {
    "close", "trade_date",
    # 复权列不需要
    "open_hfq", "open_qfq", "close_hfq", "close_qfq",
    "high_hfq", "high_qfq", "low_hfq", "low_qfq",
    "pre_close_hfq", "pre_close_qfq",
}


def build_wide_table() -> pd.DataFrame:
    """读取各源表最新分区，合并为大宽表，返回 DataFrame。"""
    reader = ParquetDataReader()

    # 1. daily_basic（主表）
    db = reader._read_latest_partition("daily_basic")
    if db is None or db.empty:
        print("[wide_table_builder] daily_basic 无数据，跳过")
        return pd.DataFrame()
    db = db.copy()
    print(f"[wide_table_builder] daily_basic: {len(db)} 行")

    # 2. stk_factor
    sf = reader._read_latest_partition("stk_factor")
    if sf is not None and not sf.empty:
        sf = sf.copy()
        # 丢弃不需要的列
        drop_cols = [c for c in STK_FACTOR_DROP if c in sf.columns]
        sf.drop(columns=drop_cols, inplace=True, errors="ignore")
        # 重命名
        rename_map = {k: v for k, v in STK_FACTOR_RENAME.items() if k in sf.columns}
        sf.rename(columns=rename_map, inplace=True)
        # 只保留 ts_code + 重命名后的因子列 + adj_factor
        keep = [c for c in STK_FACTOR_KEEP if c in sf.columns] + \
               [v for v in STK_FACTOR_RENAME.values() if v in sf.columns]
        sf = sf[keep]
        print(f"[wide_table_builder] stk_factor: {len(sf)} 行, 列={len(sf.columns)}")
        # left join
        result = db.merge(sf, on="ts_code", how="left")
    else:
        print("[wide_table_builder] stk_factor 无数据，跳过")
        result = db

    # 3. moneyflow
    mf = reader._read_latest_partition("moneyflow")
    if mf is not None and not mf.empty:
        mf = mf[["ts_code", "net_mf_amount"]].copy()
        mf.rename(columns={"net_mf_amount": "moneyflow_net_amount"}, inplace=True)
        print(f"[wide_table_builder] moneyflow: {len(mf)} 行")
        result = result.merge(mf, on="ts_code", how="left")
    else:
        print("[wide_table_builder] moneyflow 无数据，跳过")

    # 4. stock_basic（静态表）
    try:
        basic = reader.get_stock_basic()
        if basic is not None and not basic.empty:
            # 取 ts_code, name, symbol
            name_col = "name" if "name" in basic.columns else "stock_name"
            sub = basic[["ts_code", name_col, "symbol"]].copy() if "symbol" in basic.columns else \
                  basic[["ts_code", name_col]].copy()
            sub.rename(columns={name_col: "stock_name"}, inplace=True)
            result = result.merge(sub, on="ts_code", how="left")
            print(f"[wide_table_builder] stock_basic: {len(sub)} 行")
    except Exception as e:
        print(f"[wide_table_builder] stock_basic 读取失败: {e}")

    # 5. 派生 year/month/day
    if "trade_date" in result.columns:
        td = pd.to_datetime(result["trade_date"])
        result["year"] = td.dt.year
        result["month"] = td.dt.month
        result["day"] = td.dt.day

    print(f"[wide_table_builder] 合并完成: {len(result)} 行, {len(result.columns)} 列")
    return result


def main():
    df = build_wide_table()
    if df is not None and not df.empty:
        save_single_parquet(df, "stock_business.parquet")
        print(f"[wide_table_builder] 写完成: {len(df)} 行, {len(df.columns)} 列")
    else:
        print("[wide_table_builder] 无数据可写入")


if __name__ == "__main__":
    main()
