"""第三方数据源客户端（fuyao / tickflow）。

与 tushare（app/utils/db_utils.DatabaseUtils）完全独立：
- 凭证各自独立（FUYAO_API_KEY / TICKFLOW_API_KEY）
- 归一化到与 tushare 相同的 Parquet 表口径（fuyao_normalize），
  数据源只是同一张表的可替换生产者
"""

from app.utils.data_sources.fuyao_client import (
    API_KEY_ENV as FUYAO_API_KEY_ENV,
    BASE_URL as FUYAO_BASE_URL,
    FuyaoClient,
    FuyaoError,
    beijing_ms_to_ymd,
)
from app.utils.data_sources.fuyao_dump import DumpStore, FuyaoDailyFetcher
from app.utils.data_sources.fuyao_normalize import (
    daily_frame_from_dump,
    daily_frame_from_kline_rows,
    financial_items_to_frame,
    snapshot_rows_to_quote_frame,
    snapshot_rows_to_stock_basic,
)
from app.utils.data_sources.tickflow_client import (
    API_KEY_ENV as TICKFLOW_API_KEY_ENV,
    BASE_URL as TICKFLOW_BASE_URL,
    TickflowClient,
    TickflowError,
)

__all__ = [
    "FuyaoClient",
    "FuyaoError",
    "FUYAO_API_KEY_ENV",
    "FUYAO_BASE_URL",
    "beijing_ms_to_ymd",
    "DumpStore",
    "FuyaoDailyFetcher",
    "daily_frame_from_dump",
    "daily_frame_from_kline_rows",
    "financial_items_to_frame",
    "snapshot_rows_to_quote_frame",
    "snapshot_rows_to_stock_basic",
    "TickflowClient",
    "TickflowError",
    "TICKFLOW_API_KEY_ENV",
    "TICKFLOW_BASE_URL",
]
