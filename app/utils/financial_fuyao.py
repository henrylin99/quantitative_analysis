"""扶摇财务三表下载（income_statement / balance_sheet / cash_flow 的 fuyao 生产者）。

与 tushare VIP 版（financial_vip.py）写入同一组 Parquet 表，按 end_date 报告期
分区。tushare 版按报告期一次拉全市场（需要 VIP 积分），扶摇是单标的接口
（免费 key 即可），全市场一轮约 3 表 × 11 分钟（0.12s/请求节流）。

增量策略：
- expected = 最近一个已过披露截止日的报告期（Q1→4/30、H1→8/31、Q3→10/31、
  FY→次年 4/30）
- 本地最新分区已 >= expected：整表跳过
- 否则逐标的拉最近 N 期（N = latest_local 到 expected 之间的期数 + 1，上限 20），
  与已有分区按 (ts_code, end_date) 合并、保留最新 ann_date（财报更正覆盖旧值）
- 每 500 个标的一次落盘（save_to_parquet 是整分区覆盖，必须先按报告期聚合），
  中断后重跑至多重复 500 个标的的请求

已知差异：字段映射见 fuyao_normalize.INCOME_FIELD_MAP 等，扶摇未披露的字段
保持缺失（NaN），不做插补。
"""

import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 兼容直接运行（python app/utils/financial_fuyao.py）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

from app.utils.data_sources.fuyao_client import FuyaoClient
from app.utils.data_sources.fuyao_normalize import financial_items_to_frame
from app.utils.parquet_job_helpers import env_bool, latest_partition_date
from app.utils.parquet_writer import save_to_parquet

#: 扶摇表名 → 本地分区表名
TABLES = {
    "income": "income_statement",
    "balance_sheet": "balance_sheet",
    "cash_flow": "cash_flow",
}

#: 报告期（MMDD）→ 披露截止日（月, 日；FY 为次年）
DISCLOSURE_DEADLINES = {
    "0331": (4, 30),
    "0630": (8, 31),
    "0930": (10, 31),
    "1231": (4, 30),
}

QUARTER_ENDS = ("0331", "0630", "0930", "1231")
MAX_FETCH_PERIODS = 20
#: 每批标的数：批内聚合、批末落盘（断点续跑粒度）
SYMBOL_CHUNK_SIZE = 500
SYMBOL_THROTTLE_NOTE = "0.12s/请求"


def quarter_periods(start_ymd: str, end_ymd: str) -> List[str]:
    """生成 [start, end] 之间的全部季度报告期（YYYYMMDD）。"""
    periods = []
    for year in range(int(start_ymd[:4]), int(end_ymd[:4]) + 1):
        for month_day in QUARTER_ENDS:
            period = f"{year}{month_day}"
            if start_ymd <= period <= end_ymd:
                periods.append(period)
    return periods


def expected_latest_period(today: Optional[date] = None) -> Optional[str]:
    """最近一个已过披露截止日的报告期；一个都没有时返回 None。"""
    today = today or date.today()
    candidates: List[Tuple[date, str]] = []
    for year in (today.year - 1, today.year):
        for month_day, (month, day) in DISCLOSURE_DEADLINES.items():
            deadline_year = year + 1 if month_day == "1231" else year
            deadline = date(deadline_year, month, day)
            if deadline <= today:
                candidates.append((deadline, f"{year}{month_day}"))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])[1]


def resolve_fetch_periods(latest_local: Optional[str], expected: str) -> List[str]:
    """本次需要覆盖的报告期窗口（含更正重拉：从本地最新期（含）到 expected）。"""
    start = latest_local or f"{int(expected[:4]) - 5}0101"
    return quarter_periods(start, expected)


def _read_existing_partition(table: str, end_date: str, data_dir: Optional[str]) -> Optional[pd.DataFrame]:
    clean = str(end_date).replace("-", "")
    partition = Path(data_dir or ".") / table / f"year={clean[:4]}" / f"month={clean[4:6]}" / f"day={clean[6:]}" / "data.parquet"
    if not partition.exists():
        return None
    try:
        return pd.read_parquet(partition)
    except Exception as exc:  # noqa: BLE001 - 坏分区按空处理，靠新数据重建
        logger.warning(f"[financial_fuyao] 分区读取失败，将重建: {partition} ({exc})")
        return None


def _merge_partition(existing: Optional[pd.DataFrame], new: pd.DataFrame) -> pd.DataFrame:
    """同分区合并：(ts_code, end_date) 去重，保留最新 ann_date（更正覆盖旧值）。"""
    if existing is None or existing.empty:
        return new
    combined = pd.concat([existing, new], ignore_index=True)
    ann = pd.to_numeric(combined.get("ann_date"), errors="coerce")
    combined = (
        combined.assign(_ann=ann)
        .sort_values("_ann", na_position="first", kind="mergesort")
        .drop_duplicates(subset=["ts_code", "end_date"], keep="last")
        .drop(columns=["_ann"])
    )
    return combined


def all_stock_codes(client: Optional[FuyaoClient] = None) -> List[str]:
    """标的清单：优先本地 stock_basic，冷启动时回退扶摇全市场快照。"""
    from app.utils.parquet_job_helpers import get_stock_codes

    codes = get_stock_codes()
    if codes:
        return codes
    logger.warning("[financial_fuyao] 本地 stock_basic 为空，回退扶摇快照获取标的清单")
    from app.utils.data_sources.fuyao_normalize import snapshot_rows_to_stock_basic

    rows, _ = (client or FuyaoClient()).snapshot_all()
    return snapshot_rows_to_stock_basic(rows)["ts_code"].tolist()


def _sync_table(
    client: FuyaoClient,
    table: str,
    partition_table: str,
    symbols: List[str],
    limit: int,
    data_dir: Optional[str],
) -> Tuple[int, int, int]:
    """同步一张财务表，返回 (拉取成功标的数, 写入报告期数, 写入行数)。"""
    rows_by_period: Dict[str, List[pd.DataFrame]] = defaultdict(list)
    written_periods = 0
    written_rows = 0
    fetched_ok = 0

    def flush():
        nonlocal written_periods, written_rows
        for end_date in sorted(rows_by_period):
            new = pd.concat(rows_by_period[end_date], ignore_index=True)
            existing = _read_existing_partition(partition_table, end_date, data_dir)
            merged = _merge_partition(existing, new)
            written_rows += save_to_parquet(merged, end_date, partition_table, data_dir=data_dir)
            written_periods += 1
        rows_by_period.clear()

    fetched = 0
    for symbol in symbols:
        try:
            items = client.financial_statement(table, symbol, limit=limit)
        except Exception as exc:  # noqa: BLE001 - 单标的失败不阻断全市场任务
            logger.warning(f"[financial_fuyao] {table} {symbol} 拉取失败，跳过: {exc}")
            continue
        frame = financial_items_to_frame(items, table, symbol)
        fetched_ok += 1
        for end_date, group in frame.groupby("end_date"):
            rows_by_period[str(end_date)].append(group)
        if fetched_ok % SYMBOL_CHUNK_SIZE == 0:
            flush()
            logger.info(f"[financial_fuyao] {table} 进度: {fetched_ok}/{len(symbols)}")
    flush()
    return fetched_ok, written_periods, written_rows


def main() -> int:
    load_dotenv()
    data_dir = os.getenv("DATA_DIR")
    full_refresh = env_bool("DATA_JOB_FULL_REFRESH", default=False)
    today = date.today()
    client = FuyaoClient()

    symbols = all_stock_codes(client)
    if not symbols:
        print("[financial_fuyao] 无可用标的清单（stock_basic 与快照均为空）")
        return 1

    overall_exit = 0
    for table, partition_table in TABLES.items():
        latest_local = latest_partition_date(partition_table, data_dir=data_dir)
        expected = expected_latest_period(today)
        if expected is None:
            print(f"[financial_fuyao] {partition_table}: 尚无过披露截止日的报告期，跳过")
            continue
        if latest_local is not None and latest_local >= expected and not full_refresh:
            print(f"[financial_fuyao] {partition_table}: 本地 {latest_local} 已覆盖 {expected}，跳过")
            continue

        periods = resolve_fetch_periods(latest_local, expected)
        limit = min(MAX_FETCH_PERIODS, max(2, len(periods) + (0 if full_refresh else 1)))
        print(
            f"[financial_fuyao] {partition_table}: local={latest_local or '无'} expected={expected} "
            f"periods={len(periods)} limit={limit} symbols={len(symbols)} "
            f"(预计约 {len(symbols) * 0.12 / 60:.0f} 分钟)"
        )
        fetched_ok, written_periods, written_rows = _sync_table(
            client, table, partition_table, symbols, limit, data_dir
        )
        print(
            f"[financial_fuyao] {partition_table} 完成: periods={written_periods}, "
            f"total_upsert={written_rows}"
        )
        if fetched_ok == 0:
            print(f"[financial_fuyao] {partition_table}: 全部标的拉取失败，作业标记失败")
            overall_exit = 1
    return overall_exit


if __name__ == "__main__":
    sys.exit(main())
