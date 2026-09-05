"""扶摇股票清单刷新（stock_basic.parquet 的 fuyao 生产者）。

与 tushare 版（stock_basic.py）写入同一个 stock_basic.parquet。定位差异：
- 扶摇全市场快照一次拉齐（免费 key），适合日常刷新代码清单/发现新上市代码
- 快照没有股票名称字段（名称靠下游维表关联），也没有退市股（D/P 状态）
  和行业/地域/上市日期等元数据

合并策略：已有记录整体保留（tushare 元数据与退市记录不动），快照中新出现
的代码追加（list_status=L，名称待 tushare 版补齐）。名称刷新与完整元数据
仍以 tushare 版为准。
"""

import sys
from pathlib import Path

# 兼容直接运行（python app/utils/stock_basic_fuyao.py）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

from app.utils.data_sources.fuyao_client import FuyaoClient
from app.utils.data_sources.fuyao_normalize import snapshot_rows_to_stock_basic
from app.utils.parquet_writer import save_single_parquet

REL_FILENAME = "stock_basic.parquet"


def _read_existing(data_dir) -> pd.DataFrame:
    from app.utils.parquet_job_helpers import _default_data_root

    path = Path(data_dir or _default_data_root()) / REL_FILENAME
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - 坏文件按空处理重建
        logger.warning(f"[stock_basic_fuyao] 现有文件读取失败，将重建: {exc}")
        return pd.DataFrame()


def main() -> int:
    load_dotenv()
    import os

    data_dir = os.getenv("DATA_DIR")

    rows, _ = FuyaoClient().snapshot_all()
    if not rows:
        print("[stock_basic_fuyao] 快照为空，作业标记失败")
        return 1

    existing = _read_existing(data_dir)
    merged = snapshot_rows_to_stock_basic(rows, existing)
    saved = save_single_parquet(merged, REL_FILENAME, data_dir=data_dir)
    print(
        f"[stock_basic_fuyao] 完成: total={saved} (此前 {len(existing)}, "
        f"新增 {max(saved - len(existing), 0)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
