import os
from pathlib import Path

import pandas as pd

from app.utils.db_utils import DatabaseUtils


FIELDS = "ts_code,symbol,name,area,industry,list_date"


def _resolve_output_path() -> Path:
    data_dir = os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )
    return Path(data_dir) / "stock_basic.parquet"


def _normalize_list_date(df: pd.DataFrame) -> pd.DataFrame:
    if "list_date" in df.columns:
        df = df.copy()
        df["list_date"] = pd.to_datetime(df["list_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def main() -> None:
    """下载股票基础资料并写入本地 Parquet。"""
    pro = DatabaseUtils.init_tushare_api()
    df = pro.stock_basic(exchange="", list_status="L", fields=FIELDS)

    if df is None or df.empty:
        print("[stock_basic] 没有获取到股票基础资料，跳过写入。")
        return

    df = _normalize_list_date(df)
    output_path = _resolve_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, engine="pyarrow")

    print(f"[stock_basic] 完成，写入 {len(df)} 条记录 -> {output_path}")


if __name__ == "__main__":
    main()
