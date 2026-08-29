import os
from pathlib import Path

import pandas as pd

from app.utils.db_utils import DatabaseUtils


# delist_date/list_status 用于消除幸存者偏差：只下载在市(L)股票会让回测
# 整体错过历史退市股，退市前的暴跌不进入样本，收益与回撤都会系统性失真。
FIELDS = "ts_code,symbol,name,area,industry,list_date,delist_date,list_status"


def _resolve_output_path() -> Path:
    data_dir = os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )
    return Path(data_dir) / "stock_basic.parquet"


def _normalize_list_date(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("list_date", "delist_date") if c in df.columns]
    if cols:
        df = df.copy()
        for col in cols:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def main() -> None:
    """下载股票基础资料并写入本地 Parquet。

    必须同时下载 L（上市）/D（退市）/P（暂停上市）三种状态：
    只下载在市股票会让整个系统（因子、标签、回测）天然错过历史退市股，
    构成幸存者偏差——回测收益被系统性高估。
    """
    pro = DatabaseUtils.init_tushare_api()

    frames = []
    for status in ("L", "D", "P"):
        try:
            part = pro.stock_basic(exchange="", list_status=status, fields=FIELDS)
        except Exception as exc:
            print(f"[stock_basic] 下载 list_status={status} 失败: {exc}")
            continue
        if part is not None and not part.empty:
            print(f"[stock_basic] list_status={status}: {len(part)} 条")
            frames.append(part)

    if not frames:
        print("[stock_basic] 没有获取到股票基础资料，跳过写入。")
        return

    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="ts_code", keep="first")
    df = _normalize_list_date(df)
    # 原子写：stock_basic 是全库的依赖根（股票列表/行业/地域），半截文件会让
    # 所有下游 job 拿到空列表
    from app.utils.parquet_writer import atomic_write_parquet
    output_path = _resolve_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(df, str(output_path))

    print(f"[stock_basic] 完成，写入 {len(df)} 条记录 -> {output_path}")


if __name__ == "__main__":
    main()
