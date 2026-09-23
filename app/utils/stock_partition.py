"""股票分区构建工具 —— 从日期分区派生按股票分区。

日期分区（写入主路径，由各下载作业维护）：
    {data_dir}/{table}/daily/year=YYYY/month=MM/day=DD/data.parquet

股票分区（本模块派生，查询侧按 ts_code 读取时优先命中）：
    {data_dir}/{table}/stock/ts_code=XXX/data.parquet

参考 20260213 项目的 rebuild_stock_partitions.py 实现。个股历史查询
原本要扫描范围内全部日分区再把全市场数据读进内存过滤，按股票分区后
单只股票只读一个文件。查询侧集成见 ParquetDataReader._read_table。

两种重建模式：
- 全量模式（不给日期窗口）：先写 stock_staging/ 再与 stock/ 原子换名，
  旧分区保留为 stock_bak/ 直到新分区完整落盘，失败自动恢复；
- 窗口增量模式（--start-date/--end-date）：只合并窗口内的交易日到既有
  股票分区，窗口外分区不动，适合日常日更后的增量刷新。

注意：adj_factor 在本项目不是独立表，而是 stk_factor 表的字段，
别名 "adj_factor" 会解析为重建 stk_factor 的股票分区。
"""

import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from app.utils.parquet_writer import atomic_write_parquet, parquet_file_lock

# 表名 → 日期分区相对目录；股票分区固定为同名表下的 stock/ 子目录
STOCK_PARTITION_TABLES: Dict[str, str] = {
    "daily_history": "daily_history/daily",
    "daily_basic": "daily_basic/daily",
    "moneyflow": "moneyflow/daily",
    "cyq_perf": "cyq_perf/daily",
    "stk_factor": "stk_factor/daily",
}

# 兼容 20260213 项目习惯：adj_factor 是 stk_factor 的字段而非独立表
TABLE_ALIASES: Dict[str, str] = {
    "adj_factor": "stk_factor",
}

_PRIMARY_KEYS = ["ts_code", "trade_date"]
_TS_CODE_RE = re.compile(r"^[0-9A-Za-z_]+\.[0-9A-Za-z_]+$")


def resolve_table_name(table_name: str) -> str:
    """解析表名（含别名），未知表名抛 KeyError。"""
    name = TABLE_ALIASES.get(table_name, table_name)
    if name not in STOCK_PARTITION_TABLES:
        known = sorted(set(STOCK_PARTITION_TABLES) | set(TABLE_ALIASES))
        raise KeyError(f"不支持的表: {table_name}，可选: {known}")
    return name


def default_data_root() -> str:
    """与 parquet_writer 一致的数据根目录解析。"""
    return os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )


def stock_partition_dir(data_dir: str, table_name: str) -> str:
    return os.path.join(data_dir, table_name, "stock")


def stock_partition_path(data_dir: str, table_name: str, ts_code: str) -> str:
    return os.path.join(stock_partition_dir(data_dir, table_name), f"ts_code={ts_code}", "data.parquet")


def _read_date_partitions(
    rel_table: str,
    data_dir: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """读取日期分区，按目录名做日期范围裁剪，无数据时返回空 DataFrame。

    start_date/end_date 为 YYYY-MM-DD 格式；分区目录名 year=/month=/day=
    补零后与 YYYY-MM-DD 的字典序即时间序。
    """
    base = os.path.join(data_dir, rel_table)
    if not os.path.isdir(base):
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []
    for root, dirs, files in os.walk(base):
        dirs.sort()
        if "data.parquet" not in files:
            continue
        if start_date or end_date:
            dt = _partition_dir_date(root)
            if dt is None:
                continue
            if start_date and dt < start_date:
                continue
            if end_date and dt > end_date:
                continue
        path = os.path.join(root, "data.parquet")
        try:
            df = pd.read_parquet(path)
            if not df.empty:
                frames.append(df)
        except Exception as e:  # noqa: BLE001 - 坏文件跳过并由日志留痕
            logger.warning(f"[stock_rebuild] 读取分区失败，跳过 {path}: {e}")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _partition_dir_date(path: str) -> Optional[str]:
    """从分区路径提取 YYYY-MM-DD，如 .../year=2026/month=09/day=01。"""
    values = {}
    for part in path.split(os.sep):
        for key in ("year", "month", "day"):
            prefix = f"{key}="
            if part.startswith(prefix):
                values[key] = part[len(prefix):]
    if not {"year", "month", "day"}.issubset(values):
        return None
    return "{year}-{month:0>2}-{day:0>2}".format(**values)


def _normalize_group(group: pd.DataFrame) -> pd.DataFrame:
    """单只股票分区内的整理：按主键去重（新数据覆盖旧数据）、按日期排序。"""
    group = group.dropna(subset=["ts_code"])
    group = group[group["ts_code"].map(lambda c: bool(_TS_CODE_RE.match(str(c))))]
    if group.empty:
        return group
    sort_key = pd.to_datetime(group["trade_date"], errors="coerce", format="mixed")
    group = group.assign(_sort_date=sort_key).dropna(subset=["_sort_date"])
    group = (
        group.sort_values("_sort_date")
        .drop_duplicates(subset=_PRIMARY_KEYS, keep="last")
        .drop(columns=["_sort_date"])
    )
    return group.reset_index(drop=True)


def _write_one_stock(group: pd.DataFrame, path: str) -> int:
    """原子写单只股票的分区文件，返回行数。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.rebuild.tmp.{os.getpid()}"
    group.to_parquet(tmp_path, index=False, engine="pyarrow", compression="zstd")
    os.replace(tmp_path, path)
    return len(group)


def _swap_in_staging(staging: str, stock_dir: str, backup: str) -> None:
    """staging → stock 原子换名；旧 stock 保留为 backup，失败自动恢复。"""
    if os.path.isdir(stock_dir):
        if os.path.isdir(backup):
            shutil.rmtree(backup)
        os.rename(stock_dir, backup)
    try:
        os.rename(staging, stock_dir)
    except OSError:
        if os.path.isdir(backup) and not os.path.isdir(stock_dir):
            os.rename(backup, stock_dir)
        raise
    if os.path.isdir(backup):
        shutil.rmtree(backup)


def _merge_window_into_stock(
    window_df: pd.DataFrame,
    table_name: str,
    rel_table: str,
    data_dir: str,
    max_workers: int,
) -> Optional[Dict]:
    """窗口增量模式：窗口内数据按股票合并进既有股票分区。

    返回 None 表示股票分区尚未建立，调用方应转全量重建——否则合并出的
    文件只有窗口内几天数据，却能通过查询侧按最新日期判断的新鲜度检查，
    会让个股历史查询静默丢历史。

    窗口内出现股票分区里还没有的代码（新股上市、漏跑重建）时，先从
    日期分区把该代码的全量历史读出来回填，而不是只写窗口内几行。

    股票分区的写入方只有本模块（并发重建由外层 pipeline 锁互斥），
    单文件 tmp + os.replace 原子替换即可保证读方安全，无需逐文件加锁。
    """
    stock_dir = stock_partition_dir(data_dir, table_name)
    if not os.path.isdir(stock_dir):
        logger.warning(f"[stock_rebuild:{table_name}] 股票分区不存在，窗口增量转全量重建")
        return None

    # 需要回填全历史的代码：窗口内有它、股票分区里还没有它
    stock_root = Path(stock_dir)
    missing_codes = {
        str(code)
        for code in window_df["ts_code"].dropna().unique()
        if not (stock_root / f"ts_code={code}" / "data.parquet").is_file()
    }
    backfill: Dict[str, pd.DataFrame] = {}
    if missing_codes:
        logger.info(
            f"[stock_rebuild:{table_name}] 窗口内发现 {len(missing_codes)} 只无股票分区的代码，回填全历史"
        )
        full_df = _read_date_partitions(rel_table, data_dir)
        if not full_df.empty:
            hit = full_df[full_df["ts_code"].isin(missing_codes)]
            for code, group in hit.groupby("ts_code"):
                backfill[str(code)] = group

    rows, written = 0, 0
    groups = [g for _, g in window_df.groupby("ts_code")]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for group in groups:
            code = str(group["ts_code"].iloc[0])
            path = stock_partition_path(data_dir, table_name, code)
            old = backfill.get(code)
            if old is None and os.path.isfile(path):
                try:
                    old = pd.read_parquet(path)
                except Exception as e:  # noqa: BLE001 - 旧文件损坏时以窗口数据为准重建
                    logger.warning(f"[stock_rebuild] 旧股票分区读取失败，将覆盖 {path}: {e}")
                    old = None
            futures[pool.submit(_merge_and_write_stock, old, group, path)] = code
        for future in as_completed(futures):
            rows += future.result()
            written += 1
            if written % 1000 == 0:
                logger.info(f"[stock_rebuild:{table_name}] 窗口增量已合并 {written} 只股票")

    return {"table": table_name, "mode": "window", "stocks": written, "rows": rows}


def _merge_and_write_stock(old: Optional[pd.DataFrame], new_group: pd.DataFrame, path: str) -> int:
    """合并旧分区与窗口数据（新值覆盖旧值）后原子写回。"""
    if old is not None and not old.empty:
        merged = pd.concat([old, new_group], ignore_index=True)
    else:
        merged = new_group
    clean = _normalize_group(merged)
    if clean.empty:
        return 0
    return _write_one_stock(clean, path)


def rebuild_stock_partition(
    table_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_workers: int = 16,
    data_dir: Optional[str] = None,
) -> Dict:
    """从日期分区重建某张表的股票分区。

    start_date/end_date（YYYYMMDD 或 YYYY-MM-DD）给定时走窗口增量模式：
    只把窗口内的交易日合并进既有股票分区；否则走全量模式：整表重建并
    原子换名替换旧分区。
    """
    table_name = resolve_table_name(table_name)
    data_dir = data_dir or default_data_root()
    rel_table = STOCK_PARTITION_TABLES[table_name]

    started = time.time()
    lock_path = os.path.join(data_dir, "stock_rebuild.lock")
    with parquet_file_lock(lock_path):
        window_df = pd.DataFrame()
        if start_date or end_date:
            full = _read_date_partitions(
                rel_table, data_dir,
                start_date=_normalize_ymd(start_date) if start_date else None,
                end_date=_normalize_ymd(end_date) if end_date else None,
            )
            window_df = full
            if window_df.empty:
                logger.warning(f"[stock_rebuild:{table_name}] 窗口内没有日期分区数据，跳过")
                return {"table": table_name, "mode": "window", "stocks": 0, "rows": 0}
            stats = _merge_window_into_stock(
                window_df, table_name, rel_table, data_dir, max_workers
            )
            if stats is None:  # 股票分区尚未建立，转全量
                stats = _rebuild_full(table_name, rel_table, data_dir, max_workers)
        else:
            stats = _rebuild_full(table_name, rel_table, data_dir, max_workers)

    stats["seconds"] = round(time.time() - started, 1)
    print(
        f"[stock_rebuild:{table_name}] {stats['mode']} 完成: "
        f"stocks={stats['stocks']}, rows={stats['rows']}, 耗时 {stats['seconds']}s"
    )
    return stats


def _rebuild_full(table_name: str, rel_table: str, data_dir: str, max_workers: int) -> Dict:
    """全量重建：读整表日期分区 → 写 stock_staging/ → 原子换名。"""
    df = _read_date_partitions(rel_table, data_dir)
    if df.empty or "ts_code" not in df.columns:
        raise ValueError(f"[stock_rebuild:{table_name}] 日期分区为空（{data_dir}/{rel_table}），无法重建")

    table_dir = os.path.join(data_dir, table_name)
    stock_dir = os.path.join(table_dir, "stock")
    staging = os.path.join(table_dir, "stock_staging")
    backup = os.path.join(table_dir, "stock_bak")

    # 上次全量重建中断的现场：stock 缺位而备份还在，先恢复
    if os.path.isdir(backup) and not os.path.isdir(stock_dir):
        os.rename(backup, stock_dir)
        logger.warning(f"[stock_rebuild:{table_name}] 检测到未完成的换名，已从 stock_bak 恢复")

    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging, exist_ok=True)

    groups = [g for _, g in df.groupby("ts_code")]
    rows, written = 0, 0
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for group in groups:
                clean = _normalize_group(group)
                if clean.empty:
                    continue
                code = str(clean["ts_code"].iloc[0])
                path = os.path.join(staging, f"ts_code={code}", "data.parquet")
                futures[pool.submit(_write_one_stock, clean, path)] = code
            for future in as_completed(futures):
                rows += future.result()
                written += 1
                if written % 1000 == 0:
                    logger.info(f"[stock_rebuild:{table_name}] 已写入 {written}/{len(futures)} 只股票")
        _swap_in_staging(staging, stock_dir, backup)
    except Exception:
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
        raise

    return {"table": table_name, "mode": "full", "stocks": written, "rows": rows}


def rebuild_all_tables(
    max_workers: int = 16,
    data_dir: Optional[str] = None,
    table_names: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict]:
    """依次重建所有支持股票分区的表（单表失败不中断其余表）。

    start_date/end_date 透传给每张表：给定时走窗口增量合并，
    否则全量重建。
    """
    data_dir = data_dir or default_data_root()
    names = table_names or list(STOCK_PARTITION_TABLES)
    # 提前统一校验日期参数：参数格式错误应整体报错，而不是被下面的
    # 异常兜底逐表吞成 skipped
    window_start = _normalize_ymd(start_date) if start_date else None
    window_end = _normalize_ymd(end_date) if end_date else None
    results = []
    for name in names:
        try:
            results.append(
                rebuild_stock_partition(
                    name, window_start, window_end, max_workers, data_dir
                )
            )
        except ValueError as e:  # 日期分区为空等"无数据可建"：跳过而非失败
            logger.warning(f"[stock_rebuild:{name}] 跳过: {e}")
            results.append({"table": name, "mode": "skipped", "reason": str(e)})
        except Exception as e:  # noqa: BLE001 - 单表失败记录后继续
            logger.error(f"[stock_rebuild:{name}] 重建失败: {e}")
            results.append({"table": name, "mode": "failed", "error": str(e)})
    return results


def auto_rebuild_stock_partition(rel_table: str, saved_dates: List[str]) -> Optional[Dict]:
    """下载作业落盘后自动增量合并股票分区（下载 → 重建一条龙）。

    rel_table 形如 "daily_history/daily"，非日频表（财务三表等）直接忽略。
    设 DATA_JOB_AUTO_REBUILD=0 可停用。任何异常只记日志不抛出：重建失败
    时查询侧会自动回退日期分区扫描，不能因为它把下载作业标成失败。
    """
    if os.getenv("DATA_JOB_AUTO_REBUILD", "1") == "0":
        return None
    table_name = str(rel_table).split("/")[0]
    if table_name not in STOCK_PARTITION_TABLES or not saved_dates:
        return None
    try:
        return rebuild_stock_partition(
            table_name,
            start_date=min(saved_dates),
            end_date=max(saved_dates),
        )
    except Exception as e:  # noqa: BLE001 - 自动重建失败不拖累下载作业
        logger.warning(
            f"[stock_rebuild:{table_name}] 下载后自动重建失败（查询将回退日期分区）: {e}"
        )
        return None


def _normalize_ymd(date_str: str) -> str:
    clean = str(date_str).replace("-", "")
    if len(clean) != 8 or not clean.isdigit():
        raise ValueError(f"无效日期格式: {date_str}")
    return f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"
