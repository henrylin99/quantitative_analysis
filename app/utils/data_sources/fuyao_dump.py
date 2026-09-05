"""扶摇全市场日K dump 的缓存管理与三档取数策略。

取数三档（逐级降级，参考 tick-stock-panel 同名实现的策略分层）：
- 近端窗口（≤12 天）：daily-k-10d dump（约 1MB），一次下载覆盖全市场 10 个交易日
- 深窗口：daily-k 10 年全量 dump（约 172MB），缓存覆盖起点即复用、不追新 release
  （旧 release 的中段历史不会变，尾部新鲜度由 10d dump 补）
- 兜底：单标的 historical 接口（仅当未覆盖交易日 ≤5 天时启用，
  5567 只 × 0.12s 节流 ≈ 11 分钟/天，超过 5 天直接报错而不是烧两小时）

dump 缓存目录：``{DATA_DIR}/cache/fuyao/``，文件名 ``{prefix}__{release}.parquet``。
release 号取自预签名 URL 的 releases/<date>/ 路径；小 dump 下载新 release 后
清理旧版；10 年大 dump 只要覆盖请求起点就继续复用。
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from app.utils.data_sources.fuyao_client import (
    FuyaoClient,
    FuyaoError,
    beijing_ms_to_ymd,
)
from app.utils.data_sources.fuyao_normalize import (
    DAILY_COLUMNS,
    daily_frame_from_dump,
    daily_frame_from_kline_rows,
)

RECENT_DUMP_KIND = "daily-k-10d"
FULL_DUMP_KIND = "daily-k"

#: 10 年 dump 单次可覆盖的最大年限（服务端约束）
MAX_HISTORY_YEARS = 10
#: 兜底单标的接口允许的最大未覆盖交易日数
SYMBOL_FALLBACK_MAX_DATES = 5


def default_cache_dir() -> Path:
    data_dir = os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data"),
    )
    return Path(data_dir) / "cache" / "fuyao"


def _ymd_to_date(ymd: str) -> date:
    return datetime.strptime(str(ymd), "%Y%m%d").date()


def _date_to_ms_end(ymd: str) -> int:
    """YYYYMMDD → 当天（北京时间）23:59:59.999 的 epoch ms。"""
    dt = datetime.strptime(str(ymd), "%Y%m%d").replace(hour=23, minute=59, second=59, tzinfo=None)
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() * 1000) - 8 * 3600 * 1000


class DumpStore:
    """dump 文件缓存：按 release 落盘、按需下载、内存 memo。"""

    def __init__(self, client: FuyaoClient, cache_dir: Optional[Path] = None):
        self.client = client
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self._path_memo: Dict[str, Path] = {}
        self._frame_memo: Dict[str, pd.DataFrame] = {}

    def _release_re(self) -> "re.Pattern[str]":
        return re.compile(r"releases/(\d{8})/")

    def ensure_path(self, kind: str, prefix: str, reuse_old_if_covers: Optional[str] = None) -> Path:
        """确保 dump 已落盘并返回路径。

        reuse_old_if_covers: YYYYMMDD。已有旧缓存覆盖该日期时直接复用，
        不追新 release（避免深窗口高频触发时日日重下 172MB）。
        """
        memo = self._path_memo.get(kind)
        if memo is not None and memo.exists():
            return memo

        if reuse_old_if_covers:
            old = self._cached_covering(prefix, reuse_old_if_covers)
            if old is not None:
                self._path_memo[kind] = old
                return old

        info = self.client.dump_download_url(kind)
        release = self._release_re().search(str(info.get("presigned_url") or ""))
        release_tag = release.group(1) if release else "unknown"
        dest = self.cache_dir / f"{prefix}__{release_tag}.parquet"
        if not dest.exists():
            logger.info(f"[fuyao] 下载 dump {kind} (release {release_tag}) -> {dest}")
            self.client.download_dump(kind, dest)
            for old_file in self.cache_dir.glob(f"{prefix}__*.parquet"):
                if old_file.name != dest.name:
                    old_file.unlink(missing_ok=True)
        self._path_memo[kind] = dest
        return dest

    def _cached_covering(self, prefix: str, ymd: str) -> Optional[Path]:
        """返回缓存中 date_ms 覆盖 ymd 的最新文件；坏文件跳过。"""
        for path in sorted(self.cache_dir.glob(f"{prefix}__*.parquet"), reverse=True):
            try:
                dmin, _ = dump_date_range(path)
            except Exception as exc:  # noqa: BLE001 - 缓存损坏不致命
                logger.warning(f"[fuyao] 缓存文件不可读，跳过: {path} ({exc})")
                continue
            if dmin is not None and _ymd_to_date(ymd) >= dmin:
                return path
        return None

    def load_frame(self, kind: str, prefix: str, reuse_old_if_covers: Optional[str] = None) -> pd.DataFrame:
        """小 dump 整读 + 进程内 memo（10d dump/因子表体量小）。"""
        memo = self._frame_memo.get(kind)
        if memo is not None:
            return memo
        path = self.ensure_path(kind, prefix, reuse_old_if_covers=reuse_old_if_covers)
        frame = pd.read_parquet(path)
        self._frame_memo[kind] = frame
        return frame


def dump_date_range(path: Path) -> Tuple[Optional[date], Optional[date]]:
    """读 dump 的 date_ms 边界（只读单列，避免整读大文件）。"""
    series = pd.read_parquet(path, columns=["date_ms"])["date_ms"]
    if series.empty:
        return None, None
    dmin = beijing_ms_to_ymd(series.min())
    dmax = beijing_ms_to_ymd(series.max())
    return (
        datetime.strptime(dmin, "%Y%m%d").date() if dmin else None,
        datetime.strptime(dmax, "%Y%m%d").date() if dmax else None,
    )


class FuyaoDailyFetcher:
    """按交易日列表取全市场日K，三档策略自动降级。

    返回 {trade_date: DataFrame(tushare 口径)}；无法覆盖的日期会抛
    FuyaoError（调用方按作业失败处理，缺口由下一轮 gap_fill 回补）。
    """

    def __init__(
        self,
        client: Optional[FuyaoClient] = None,
        store: Optional[DumpStore] = None,
    ):
        self.client = client or FuyaoClient()
        self.store = store or DumpStore(self.client)

    def fetch_dates(self, trade_dates: List[str]) -> Dict[str, pd.DataFrame]:
        wanted = sorted({str(d) for d in trade_dates})
        if not wanted:
            return {}

        result = self._fetch_from_recent_dump(wanted)
        missing = [d for d in wanted if d not in result]
        if missing:
            result.update(self._fetch_from_full_dump(missing, result))
        missing = [d for d in wanted if d not in result]
        if missing:
            self._fetch_from_symbol_api(missing, result)
        return {d: result[d] for d in wanted if d in result}

    # ---- 档 1：10d dump ----

    def _fetch_from_recent_dump(self, wanted: List[str]) -> Dict[str, pd.DataFrame]:
        span_days = (_ymd_to_date(wanted[-1]) - _ymd_to_date(wanted[0])).days
        if span_days > 12:
            return {}
        try:
            dump = self.store.load_frame(RECENT_DUMP_KIND, "daily_k_10d")
        except FuyaoError as exc:
            logger.warning(f"[fuyao] 10d dump 不可用，尝试 10 年 dump: {exc}")
            return {}
        dmin = beijing_ms_to_ymd(dump["date_ms"].min())
        dmax = beijing_ms_to_ymd(dump["date_ms"].max())
        if dmin is None or dmax is None or wanted[0] < dmin or wanted[-1] > dmax:
            logger.info(f"[fuyao] 10d dump 覆盖 [{dmin}~{dmax}]，不满足窗口 [{wanted[0]}~{wanted[-1]}]")
            return {}
        frame = daily_frame_from_dump(dump, wanted)
        return self._split_by_date(frame)

    # ---- 档 2：10 年全量 dump（+ 10d dump 补尾）----

    def _fetch_from_full_dump(
        self, missing: List[str], already: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        start_ymd = missing[0]
        if (_ymd_to_date(missing[-1]) - _ymd_to_date(start_ymd)).days > MAX_HISTORY_YEARS * 365:
            raise FuyaoError(
                "window_too_long",
                f"回补窗口早于扶摇 dump 覆盖范围（>10 年）: {start_ymd}~{missing[-1]}",
            )
        try:
            path = self.store.ensure_path(
                FULL_DUMP_KIND, "daily_k", reuse_old_if_covers=start_ymd
            )
        except FuyaoError as exc:
            logger.warning(f"[fuyao] 10 年 dump 不可用: {exc}")
            return {}

        dmin, dmax = dump_date_range(path)
        result: Dict[str, pd.DataFrame] = {}
        covered = [d for d in missing if dmin and dmax and dmin <= _ymd_to_date(d) <= dmax]
        if covered:
            big = pd.read_parquet(path)
            frame = daily_frame_from_dump(big, covered)
            result = self._split_by_date(frame)

        # 大 dump 末端之后的日期由 10d dump 补尾。10d dump 覆盖最近 10 个交易日，
        # 其窗口起点即含大 dump 尾日，补尾日的 pre_close 在小 dump 内推导即为正确值。
        dmax_ymd = dmax.strftime("%Y%m%d") if dmax else ""
        tail = [d for d in missing if not dmax_ymd or d > dmax_ymd]
        if tail:
            try:
                small = self.store.load_frame(RECENT_DUMP_KIND, "daily_k_10d")
            except FuyaoError as exc:
                logger.warning(f"[fuyao] 补尾失败，10d dump 不可用: {exc}")
                return result
            small_dmin = beijing_ms_to_ymd(small["date_ms"].min())
            small_dmax = beijing_ms_to_ymd(small["date_ms"].max())
            tail_ok = [
                d for d in tail
                if small_dmin and small_dmax and small_dmin <= d <= small_dmax
            ]
            if tail_ok:
                tail_frame = daily_frame_from_dump(small, tail_ok)
                result.update(self._split_by_date(tail_frame))
        return result

    # ---- 档 3：单标的接口兜底 ----

    def _fetch_from_symbol_api(self, missing: List[str], result: Dict[str, pd.DataFrame]) -> None:
        if len(missing) > SYMBOL_FALLBACK_MAX_DATES:
            raise FuyaoError(
                "dates_not_covered",
                f"{len(missing)} 个交易日超出 dump 覆盖且超过兜底上限 "
                f"{SYMBOL_FALLBACK_MAX_DATES} 天，请检查 dump 缓存或改用显式窗口: {missing[:5]}...",
            )
        symbols = _all_stock_codes()
        if not symbols:
            raise FuyaoError("no_symbols", "stock_basic 为空，无法执行单标的兜底拉取")
        logger.warning(
            f"[fuyao] {len(missing)} 个交易日 dump 未覆盖，走单标的接口兜底"
            f"（{len(symbols)} 只 × {len(missing)} 天，预计约 "
            f"{len(symbols) * len(missing) * 0.12 / 60:.0f} 分钟）"
        )
        start_ms = _window_start_ms(_backoff_ymd(missing[0], days=10))
        end_ms = _date_to_ms_end(missing[-1])
        total = len(symbols)
        for index, ts_code in enumerate(symbols, start=1):
            try:
                rows = self.client.historical_kline(ts_code, start_ms=start_ms, end_ms=end_ms)
            except FuyaoError as exc:
                logger.warning(f"[fuyao] {ts_code} 日K拉取失败，跳过: {exc}")
                continue
            frame = daily_frame_from_kline_rows(rows, ts_code)
            frame = frame[frame["trade_date"].isin(missing)]
            for trade_date, group in frame.groupby("trade_date"):
                existing = result.get(trade_date)
                result[trade_date] = (
                    pd.concat([existing, group], ignore_index=True) if existing is not None else group
                )
            if index % 500 == 0:
                logger.info(f"[fuyao] 单标的兜底进度: {index}/{total}")
        for trade_date in missing:
            frame = result.get(trade_date)
            if frame is not None:
                result[trade_date] = frame[DAILY_COLUMNS].reset_index(drop=True)

    @staticmethod
    def _split_by_date(frame: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        if frame.empty:
            return {}
        return {
            str(trade_date): group.reset_index(drop=True)
            for trade_date, group in frame.groupby("trade_date", sort=True)
        }


def _backoff_ymd(ymd: str, days: int) -> str:
    """回退若干自然日，给单标的接口的窗口留出前一交易日上下文（推导 pre_close）。"""
    return (_ymd_to_date(ymd) - timedelta(days=days)).strftime("%Y%m%d")


def _window_start_ms(ymd: str) -> int:
    """YYYYMMDD → 当天（北京时间）00:00 的 epoch ms。"""
    dt = datetime.strptime(str(ymd), "%Y%m%d")
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() * 1000) - 8 * 3600 * 1000


def _all_stock_codes() -> List[str]:
    """从本地 stock_basic 读全量代码（含退市股，兜底口径与 tushare 对齐）。"""
    from app.services.data_reader import ParquetDataReader

    df = ParquetDataReader().get_stock_basic()
    if df.empty or "ts_code" not in df.columns:
        return []
    return df["ts_code"].dropna().astype(str).tolist()
