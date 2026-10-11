"""日内因子计算作业（批次 3.3）。

从 5min 分钟线计算 ~10 个日内因子，经 FactorEngine 截面标准化后写入
factor_values，IC 分析/分位回测/因子体检直接可消费。

环境变量（ScriptRunner 注入，与既有作业一致）：
- DATA_JOB_TRADE_DATE          单日模式（缺省=最新已落盘分钟分区日）
- DATA_JOB_START_DATE/_END_DATE 区间模式：逐交易日计算（只算有 5min 分区的日子）

Usage:
    python app/utils/intraday_factor_compute.py
    DATA_JOB_TRADE_DATE=20261009 python app/utils/intraday_factor_compute.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger

from app.services.intraday_factor_service import IntradayFactorService, datetime_of


def _env_ymd(name: str) -> str | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return datetime_of(raw).replace("-", "")


def _existing_minute_days(data_dir: str, start: str, end: str) -> list[str]:
    """区间内有 5min 分区的交易日（YYYYMMDD 升序）。"""
    days = []
    base = Path(data_dir) / "stock_minute" / "5min"
    for parquet in base.glob("year=*/*=*/*=*/data.parquet"):
        ymd = f"{parquet.parent.parent.parent.name[5:]}{parquet.parent.parent.name[6:]}{parquet.parent.name[4:]}"
        if start <= ymd <= end:
            days.append(ymd)
    return sorted(set(days))


def main() -> int:
    data_dir = os.getenv("DATA_DIR", "data")
    service = IntradayFactorService(data_dir=data_dir)

    trade_date = _env_ymd("DATA_JOB_TRADE_DATE")
    start = _env_ymd("DATA_JOB_START_DATE")
    end = _env_ymd("DATA_JOB_END_DATE")

    if trade_date:
        days = [trade_date]
    elif start and end:
        days = _existing_minute_days(data_dir, start, end)
    else:
        # 缺省：最新已落盘的 5min 分区日（盘后链路语义：当日）
        base = Path(data_dir) / "stock_minute" / "5min"
        candidates = sorted(base.glob("year=*/*=*/*=*/data.parquet"))
        if not candidates:
            print("[intraday_factor_compute] 无 5min 分区，退出")
            return 1
        latest = candidates[-1]
        ymd = f"{latest.parent.parent.parent.name[5:]}{latest.parent.parent.name[6:]}{latest.parent.name[4:]}"
        days = [ymd]

    ok_days = failed = empty_days = 0
    for day in days:
        result = service.compute_and_save(day)
        if result.get("success"):
            ok_days += 1
        elif result.get("rows") == 0:
            empty_days += 1
        else:
            failed += 1
        logger.info(f"[intraday_factor_compute] {day}: {result.get('message')}")

    print(f"[intraday_factor_compute] 完成：成功 {ok_days} / 空 {empty_days} / 失败 {failed}（共 {len(days)} 天）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
