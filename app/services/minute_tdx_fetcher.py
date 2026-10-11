"""pytdx 分钟线取数器：动态主机探测 + 分页回填（批次 3.2 唯一数据源）。

背景（2026-10-11 实测，详见记忆 minute-kline-source-pytdx-only）：
- 通达信公共行情服务器 IP 经常更换；`tongdaxin/client.py` 的 4 个硬编码
  DEFAULT_HOSTS 已半死（TCP 可连、count 命令有响应，但 bars/quotes 返回 None）；
- pytdx 内置 hq_hosts 池 104 台，可用主机集中在后半段国泰君安块
  （117.34.114.13~27:7709），周末也稳定返回真实 bars。

探测纪律：**必须用真实 bars 调用验证**（连上 ≠ 能取数），仅 TCP 握手
成功不算可用。可用主机列表缓存 `data/minute_sync/tdx_host.json`，取数
失败时先轮换列表内主机，列表耗尽再全池重扫。

分页：get_security_bars 单次 ≤800 根（5min ≈ 16 个交易日），回填按
start 偏移向后翻页直至覆盖 start_date（6 个月 ≈ 8 页）。
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from loguru import logger

from app.services.tongdaxin.bars import normalize_tdx_minute_bars
from app.services.tongdaxin.code_mapping import any_style_code_to_tdx

#: 主机缓存路径（相对于 DATA_DIR）
_HOST_CACHE_REL = Path("minute_sync") / "tdx_host.json"
#: 探测线程数（全池 104 台并行扫，1~2 分钟内完成）
_PROBE_WORKERS = 16
_PROBE_TIMEOUT = 4
#: 每页根数（服务端单次上限 800）
_PAGE_BARS = 800


def _load_hq_hosts() -> List[Tuple[str, str, int]]:
    """pytdx 内置主机池 → [(name, ip, port)]。"""
    try:
        from pytdx.config.hosts import hq_hosts

        return [(str(name), str(ip), int(port)) for name, ip, port in hq_hosts]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"读取 pytdx hq_hosts 失败: {exc}")
        return []


def _probe_host(entry: Tuple[str, str, int]) -> Optional[Tuple[str, str, int]]:
    """单台主机探测：连接 + 真实 5min bars 验证。"""
    name, ip, port = entry
    try:
        from pytdx.hq import TdxHq_API

        api = TdxHq_API()
        if not api.connect(ip, port, time_out=_PROBE_TIMEOUT):
            return None
        try:
            # 沪市 600000 的 5min bars 是全市场都有数据的"金丝雀"
            bars = api.get_security_bars(0, 1, "600000", 0, 5)
            return (name, ip, port) if bars else None
        finally:
            api.disconnect()
    except Exception:  # noqa: BLE001
        return None


class TdxMinuteFetcher:
    """逐股分钟线取数：主机缓存 → 轮换 → 全池重扫。"""

    def __init__(self, data_dir: str | None = None, host_cache_path: str | None = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = Path(data_dir)
        self.host_cache_path = Path(host_cache_path) if host_cache_path else self.data_dir / _HOST_CACHE_REL
        self._api = None
        self._host: Optional[Tuple[str, str, int]] = None
        self._fallback_hosts: List[Tuple[str, str, int]] = []

    # ---- 主机管理 ----

    def _read_cache(self) -> Optional[dict]:
        if not self.host_cache_path.is_file():
            return None
        try:
            return json.loads(self.host_cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def _write_cache(self) -> None:
        payload = {
            "verified_at": datetime.now().isoformat(timespec="seconds"),
            "current": list(self._host) if self._host else None,
            "fallbacks": [list(h) for h in self._fallback_hosts],
        }
        self.host_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.host_cache_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.host_cache_path)

    def ensure_host(self, force_rescan: bool = False) -> Tuple[str, str, int]:
        """返回当前可用主机；缓存有效直接复用，失效先轮换 fallback 再全池重扫。"""
        if self._host is not None and not force_rescan:
            return self._host

        cache = None if force_rescan else self._read_cache()
        if cache:
            current = cache.get("current")
            fallbacks = [tuple(h) for h in cache.get("fallbacks") or []]
            if current:
                self._host = tuple(current)
                self._fallback_hosts = [h for h in fallbacks if h != self._host]
                if self._connect_current():
                    logger.info(f"pytdx 复用缓存主机 {self._host[1]}:{self._host[2]}")
                    return self._host
                logger.warning(f"缓存主机 {self._host[1]} 已失效，轮换 fallback")
                self._host = None
            for candidate in self._fallback_hosts:
                self._host = candidate
                if self._connect_current():
                    self._write_cache()
                    logger.info(f"pytdx 轮换到主机 {candidate[1]}:{candidate[2]}")
                    return self._host
                self._host = None

        return self._scan_and_pick()

    def _scan_and_pick(self) -> Tuple[str, str, int]:
        hosts = _load_hq_hosts()
        if not hosts:
            raise ConnectionError("pytdx 主机池为空，无法探测")
        logger.info(f"pytdx 全池扫描 {len(hosts)} 台主机（{os.getenv('TDX_PROBE_WORKERS', str(_PROBE_WORKERS))} 并发）…")
        workers = int(os.getenv("TDX_PROBE_WORKERS", str(_PROBE_WORKERS)))
        working: List[Tuple[str, str, int]] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(_probe_host, hosts):
                if result:
                    working.append(result)
        if not working:
            raise ConnectionError("pytdx 全池扫描无可用主机（服务器 IP 可能整体更换，需更新 hq_hosts）")
        self._host = working[0]
        self._fallback_hosts = working[1:]
        self._connect_current()
        self._write_cache()
        logger.info(f"pytdx 探测到 {len(working)} 台可用主机，选用 {self._host[1]}:{self._host[2]}")
        return self._host

    def _connect_current(self) -> bool:
        try:
            from pytdx.hq import TdxHq_API

            self._api = TdxHq_API()
            name, ip, port = self._host
            return bool(self._api.connect(ip, port, time_out=5))
        except Exception:  # noqa: BLE001
            self._api = None
            return False

    def _api_or_rotate(self):
        """当前连接取数失败时轮换主机，返回重连后的 api（或 None 表示全废）。"""
        if self._host is None:
            self.ensure_host()
        if self._api is not None:
            return self._api
        for candidate in list(self._fallback_hosts):
            self._host = candidate
            if self._connect_current():
                self._write_cache()
                return self._api
        self._scan_and_pick()
        return self._api

    # ---- 取数 ----

    def fetch_latest(self, ts_code: str, period_type: str = "5min", limit: int = 600) -> pd.DataFrame:
        """最近 limit 根分钟 bar（增量同步入口）。"""
        return self._fetch_paged(ts_code, period_type, pages=1, page_bars=limit)

    def fetch_range(self, ts_code: str, period_type: str, start_date: str) -> pd.DataFrame:
        """回填：向前翻页直至覆盖 start_date（YYYYMMDD）。"""
        return self._fetch_paged(ts_code, period_type, start_date=start_date)

    def _fetch_paged(
        self,
        ts_code: str,
        period_type: str,
        pages: int = 0,
        page_bars: int = _PAGE_BARS,
        start_date: str | None = None,
    ) -> pd.DataFrame:
        market, code = any_style_code_to_tdx(ts_code)
        from app.services.tongdaxin.bars import period_type_to_tdx_category

        category = period_type_to_tdx_category(period_type)

        frames: List[pd.DataFrame] = []
        floor = None
        if start_date:
            floor = pd.Timestamp(datetime.strptime(start_date, "%Y%m%d"))
        max_start = 0 if not start_date else 14000  # 约 2.5 年，防失控

        start = 0
        while True:
            api = self._api_or_rotate()
            if api is None:
                raise ConnectionError("pytdx 无可用主机，取数中止")
            payload = api.get_security_bars(category, market, code, start, page_bars) or []
            if not payload:
                break
            df = normalize_tdx_minute_bars(payload, market=market, code=code, period_type=period_type)
            if not df.empty:
                frames.append(df)
                earliest = df["datetime"].min()
                if floor is not None and earliest <= floor:
                    break
            start += page_bars
            if start > max_start or (pages and start >= pages * page_bars):
                break

        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["datetime"]).sort_values("datetime")
        if floor is not None:
            result = result[result["datetime"] >= floor]
        result = result.reset_index(drop=True)
        # 分页边界上 normalize 的 shift(1) 会用本页首行自身收盘当 pre_close，
        # 合并后按全序列重算一遍
        result["pre_close"] = result["close"].shift(1)
        first = result["pre_close"].isna()
        result.loc[first, "pre_close"] = result.loc[first, "close"]
        result["change"] = result["close"] - result["pre_close"]
        result["pct_chg"] = (result["change"] / result["pre_close"] * 100).fillna(0).round(4)
        result.loc[first, ["change", "pct_chg"]] = [0, 0]
        return result
