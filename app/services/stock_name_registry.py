"""股票名称注册表：本地 stock_basic + TickFlow 标的维表合并。

扶摇行情快照本身不带名称；stock_basic 由 tushare/fuyao job 离线维护，
新股或存量数据陈旧时会缺名称。TickFlow free 档的交易所标的维表
（``GET /v1/exchanges/{SH,SZ,BJ}/instruments``）带全量 A 股名称，
拉一次落盘 parquet 缓存（默认 7 天刷新），与 stock_basic 合并后
作为全站名称兜底：stock_basic 优先（与现有展示一致），缺失处用
TickFlow 补齐。

缓存路径：``{DATA_DIR}/cache/tickflow/instruments.parquet``，
损坏/缺失/过期时后台重拉，拉取失败静默降级为仅 stock_basic。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

CACHE_TTL_SECONDS = 7 * 24 * 3600.0
EXCHANGES = ("SH", "SZ", "BJ")


def default_cache_dir() -> Path:
    data_dir = os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data"),
    )
    return Path(data_dir) / "cache" / "tickflow"


def _cache_path() -> Path:
    return default_cache_dir() / "instruments.parquet"


def fetch_tickflow_names(client=None) -> Dict[str, str]:
    """从 TickFlow 拉三交易所标的维表，返回 {ts_code: name}（失败抛异常）。"""
    from app.utils.data_sources.tickflow_client import TickflowClient

    client = client or TickflowClient()
    names: Dict[str, str] = {}
    for exchange in EXCHANGES:
        for item in client.instruments(exchange=exchange):
            symbol = str(item.get("symbol") or "").strip()
            name = str(item.get("name") or "").strip()
            if symbol and name:
                names[symbol] = name
    if not names:
        raise RuntimeError("TickFlow 标的维表为空")
    return names


def _read_cache(path: Path, max_age_seconds: float) -> Optional[Dict[str, str]]:
    try:
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        if time.time() - mtime > max_age_seconds:
            return None
        frame = pd.read_parquet(path)
        if frame.empty or "ts_code" not in frame.columns or "name" not in frame.columns:
            return None
        return dict(zip(frame["ts_code"].astype(str), frame["name"].astype(str)))
    except Exception as exc:  # noqa: BLE001 - 缓存坏了等同于没有缓存
        logger.debug(f"[names] tickflow 名称缓存读取失败: {exc}")
        return None


def _write_cache(path: Path, names: Dict[str, str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame({"ts_code": list(names.keys()), "name": list(names.values())})
        tmp = path.with_suffix(f".parquet.part.{os.getpid()}")
        frame.to_parquet(tmp, index=False)
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001 - 缓存写失败不影响名称供应
        logger.debug(f"[names] tickflow 名称缓存写入失败: {exc}")


class StockNameRegistry:
    """进程内单例（get_stock_name_registry）：名称合并 + TickFlow 兜底缓存。"""

    def __init__(self, cache_path: Optional[Path] = None):
        self._cache_path = Path(cache_path) if cache_path else _cache_path()
        self._lock = threading.Lock()
        self._names: Optional[Dict[str, str]] = None
        self._fetched_monotonic: float = 0.0

    def name_map(self, max_age_seconds: float = CACHE_TTL_SECONDS) -> Dict[str, str]:
        """合并名称表（stock_basic 优先，TickFlow 补缺；带进程内缓存）。"""
        with self._lock:
            if self._names is not None and time.monotonic() - self._fetched_monotonic < 300.0:
                return self._names

        merged: Dict[str, str] = {}
        tickflow_names = _read_cache(self._cache_path, max_age_seconds)
        if tickflow_names is None:
            try:
                tickflow_names = fetch_tickflow_names()
                _write_cache(self._cache_path, tickflow_names)
            except Exception as exc:  # noqa: BLE001 - 兜底源失败降级 stock_basic
                logger.debug(f"[names] tickflow 标的维表拉取失败: {exc}")
                tickflow_names = {}
        merged.update(tickflow_names)

        try:
            from app.services.data_reader import ParquetDataReader

            basic = ParquetDataReader().get_stock_basic()
            if not basic.empty and "ts_code" in basic.columns and "name" in basic.columns:
                merged.update(
                    dict(zip(basic["ts_code"].astype(str), basic["name"].astype(str)))
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[names] stock_basic 名称读取失败: {exc}")

        with self._lock:
            self._names = merged
            self._fetched_monotonic = time.monotonic()
        return merged

    def merge_names(self, rows: List[Dict]) -> List[Dict]:
        """就地补齐 rows 里缺失的 name 字段（无名称表时原样返回）。"""
        try:
            name_map = self.name_map()
        except Exception:  # noqa: BLE001
            return rows
        for row in rows:
            if row.get("name") is None:
                row["name"] = name_map.get(str(row.get("ts_code")))
        return rows

    def invalidate(self) -> None:
        """清空进程内缓存（测试/手动刷新用；不影响落盘缓存）。"""
        with self._lock:
            self._names = None
            self._fetched_monotonic = 0.0


_registry: Optional[StockNameRegistry] = None
_registry_lock = threading.Lock()


def get_stock_name_registry() -> StockNameRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = StockNameRegistry()
        return _registry
