"""板块与连板分析服务：涨停池 / 连板天梯 / 同花顺行业·概念板块。

数据全部来自扶摇特色数据域：
- 涨停池 ``limit-up-pool``：按交易日的涨停个股（连板数/封单额/涨停时间/原因）
- 连板天梯 ``limit-up-ladder``：近 30 个交易日的 2 板~7 板+ 矩阵
- 同花顺指数目录+快照：行业（320 个）/概念（390 个）板块的实时涨跌排行
- 指数成分股：板块成分清单，用全市场快照帧富化个股行情

缓存策略：
- 涨停池按（日期,页）缓存，盘中 60s、历史日永久（当日数据不再变化）
- 天梯/板块快照分别 5 分钟 / 60 秒；目录与成分股按小时~天缓存
- 扶摇异常时优先回供过期缓存（stale 标记），无缓存才抛错
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.utils.data_sources.fuyao_client import BEIJING_TZ, FuyaoClient, FuyaoError

POOL_FRESH_SECONDS = 60.0
LADDER_FRESH_SECONDS = 300.0
BOARD_SNAPSHOT_FRESH_SECONDS = 60.0
CATALOG_FRESH_SECONDS = 6 * 3600.0
CONSTITUENTS_FRESH_SECONDS = 3600.0
TRADING_DAYS_FRESH_SECONDS = 6 * 3600.0
STALE_SERVE_SECONDS = 3600.0

#: 天梯矩阵的档位键 → 连板数
LADDER_BOARD_KEYS = (
    ("two_board", 2),
    ("three_board", 3),
    ("four_board", 4),
    ("five_board", 5),
    ("six_board", 6),
    ("seven_over", 7),
)

VALID_TAGS = ("industry", "cn_concept")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ymd_to_beijing_ms(ymd: str) -> int:
    """YYYYMMDD → 北京时间当日零点 epoch ms（扶摇 date_ms 口径）。"""
    dt = datetime.strptime(str(ymd), "%Y%m%d").replace(tzinfo=BEIJING_TZ)
    return int(dt.timestamp() * 1000)


class BoardMarketService:
    """进程内单例（get_board_market_service），线程安全。"""

    def __init__(self, client: Optional[FuyaoClient] = None):
        self._client = client
        self._lock = threading.Lock()
        self._pool_cache: Dict[Tuple[str, int, int], Tuple[float, Dict[str, Any]]] = {}
        self._ladder_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._catalog_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._boards_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._constituents_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._trade_days_cache: Optional[Tuple[float, List[str]]] = None

    @property
    def client(self) -> FuyaoClient:
        if self._client is None:
            self._client = FuyaoClient()
        return self._client

    @staticmethod
    def _serve_stale(
        cached: Optional[Tuple[float, Dict[str, Any]]], fresh_seconds: float, exc: Exception
    ) -> Optional[Dict[str, Any]]:
        """新鲜期过期后 1 小时内回供旧值（标 stale），超出窗口返回 None。"""
        if cached and time.monotonic() - cached[0] < fresh_seconds + STALE_SERVE_SECONDS:
            logger.warning(f"[board] 扶摇拉取失败，回供过期缓存: {exc}")
            payload = dict(cached[1])
            payload.update({"cached": True, "stale": True})
            return payload
        return None

    # ---- 交易日辅助 ----

    def latest_trade_date(self) -> str:
        """最近交易日 YYYYMMDD（交易日历缓存 6 小时；异常回退自然日回退）。"""
        with self._lock:
            cached = self._trade_days_cache
        if cached and time.monotonic() - cached[0] < TRADING_DAYS_FRESH_SECONDS:
            return cached[1][-1]
        try:
            rows = self.client.trading_days()
            days = sorted(
                str(row.get("date") or "") for row in rows if row.get("date")
            )
            days = [d for d in days if len(d) == 8 and d <= self._today()]
            if not days:
                raise FuyaoError("empty", "交易日历为空")
            with self._lock:
                self._trade_days_cache = (time.monotonic(), days)
            return days[-1]
        except FuyaoError as exc:
            logger.warning(f"[board] 交易日历获取失败，回退自然日: {exc}")
            return self._fallback_trade_date()

    @staticmethod
    def _today() -> str:
        return datetime.now(BEIJING_TZ).strftime("%Y%m%d")

    @staticmethod
    def _fallback_trade_date() -> str:
        """无交易日历时按自然日回退（周末向前找周五），够用且不依赖网络。"""
        day = datetime.now(BEIJING_TZ).date()
        while day.weekday() >= 5:  # 5=周六 6=周日
            day -= timedelta(days=1)
        return day.strftime("%Y%m%d")

    # ---- 涨停池 / 连板天梯 ----

    def get_limit_up_pool(self, date: Optional[str] = None, page: int = 1, size: int = 100) -> Dict[str, Any]:
        """涨停池（date YYYYMMDD 可空=最近交易日；连板数降序）。

        返回 {date,total,page,size,items:[...],stale?}；扶摇异常时回供
        1 小时内的过期缓存。
        """
        resolved = self._validate_date(date) or self.latest_trade_date()
        key = (resolved, page, min(int(size), 200))
        with self._lock:
            cached = self._pool_cache.get(key)
        if cached and time.monotonic() - cached[0] < self._pool_fresh_seconds(resolved):
            payload = dict(cached[1])
            payload["cached"] = True
            return payload

        try:
            data = self.client.limit_up_pool(
                date_ms=_ymd_to_beijing_ms(resolved), page=key[1], size=key[2]
            )
            pagination = data.get("pagination") or {}
            items = self._normalize_pool_items(data.get("item") or [])
            payload = {
                "date": resolved,
                "total": int(pagination.get("total") or len(items)),
                "page": key[1],
                "size": key[2],
                "items": items,
            }
            with self._lock:
                self._pool_cache[key] = (time.monotonic(), payload)
            return payload
        except FuyaoError as exc:
            fresh = self._pool_fresh_seconds(resolved)
            stale = self._serve_stale(cached, fresh, exc)
            if stale is not None:
                return stale
            raise

    @staticmethod
    def _pool_fresh_seconds(date: str) -> float:
        """历史日数据不再变化，缓存视为永久新鲜；仅当日短缓存。"""
        today = datetime.now(BEIJING_TZ).strftime("%Y%m%d")
        return POOL_FRESH_SECONDS if date >= today else 24 * 3600.0

    @staticmethod
    def _normalize_pool_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """字段重命名为前端友好蛇形（保留原始含义，见 client docstring）。"""
        normalized = []
        for row in items:
            normalized.append(
                {
                    "ts_code": row.get("thscode"),
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "is_st": bool(row.get("is_st")),
                    "is_new": bool(row.get("is_new")),
                    "last_price": row.get("last_price"),
                    "pct_chg": row.get("price_change_ratio_pct"),
                    "limit_up_time": row.get("limit_up_time"),
                    "reason": row.get("limit_up_reason"),
                    "continue_day_text": row.get("continue_day_text"),
                    "continue_day_cnt": row.get("continue_day_cnt"),
                    "seal_money": row.get("seal_money"),
                    "max_seal_money": row.get("max_seal_money"),
                }
            )
        return normalized

    def get_limit_up_ladder(self) -> Dict[str, Any]:
        """连板天梯：30 个交易日的 {date, counts:{连板数:家数}, highest}。"""
        with self._lock:
            cached = self._ladder_cache
        if cached and time.monotonic() - cached[0] < LADDER_FRESH_SECONDS:
            return cached[1]
        try:
            data = self.client.limit_up_ladder()
        except FuyaoError as exc:
            stale = self._serve_stale(cached, LADDER_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise
        days = []
        for day in data.get("item") or []:
            boards = day.get("boards") or {}
            counts = {
                str(num): len(boards.get(key) or []) for key, num in LADDER_BOARD_KEYS
            }
            highest = max(
                (int(num) for key, num in LADDER_BOARD_KEYS if boards.get(key)),
                default=0,
            )
            days.append(
                {
                    "date": day.get("date"),
                    "counts": counts,
                    "highest": highest,
                    "total": sum(counts.values()),
                }
            )
        payload = {"days": days}
        with self._lock:
            self._ladder_cache = (time.monotonic(), payload)
        return payload

    # ---- 同花顺行业 / 概念板块 ----

    def get_boards(self, tag: str) -> Dict[str, Any]:
        """板块涨跌排行（tag: industry/cn_concept；按涨跌幅降序）。

        目录缓存 6 小时，行情快照缓存 60 秒；快照失败的板块留在
        unavailable 列表里而不是悄悄消失。
        """
        if tag not in VALID_TAGS:
            raise ValueError(f"tag 取值须为 {'/'.join(VALID_TAGS)}")
        catalog = self._get_catalog(tag)
        with self._lock:
            cached = self._boards_cache.get(tag)
        if cached and time.monotonic() - cached[0] < BOARD_SNAPSHOT_FRESH_SECONDS:
            payload = dict(cached[1])
            payload["cached"] = True
            return payload

        codes = [str(row.get("thscode")) for row in catalog if row.get("thscode")]
        quote_by_code: Dict[str, Dict[str, Any]] = {}
        last_error: Optional[FuyaoError] = None
        for start in range(0, len(codes), 100):
            batch = codes[start:start + 100]
            try:
                rows, _ = self.client.index_snapshot(batch)
            except FuyaoError as exc:
                logger.warning(f"[board] 板块快照批次失败（{len(batch)} 只）: {exc}")
                last_error = exc
                continue
            for row in rows:
                quote_by_code[str(row.get("thscode"))] = row

        if not quote_by_code:
            stale = self._serve_stale(cached, BOARD_SNAPSHOT_FRESH_SECONDS, last_error)
            if stale is not None:
                return stale
            raise last_error or FuyaoError("empty", "板块快照为空")

        items: List[Dict[str, Any]] = []
        unavailable: List[str] = []
        for row in catalog:
            code = str(row.get("thscode"))
            quote = quote_by_code.get(code)
            if quote is None:
                unavailable.append(code)
                continue
            items.append(
                {
                    "thscode": code,
                    "name": row.get("name"),
                    "last_price": quote.get("last_price"),
                    "pct_chg": quote.get("price_change_ratio_pct"),
                    "turnover_yuan": quote.get("turnover"),
                    "volume": quote.get("volume"),
                }
            )
        items.sort(key=lambda x: (x["pct_chg"] is None, -(x["pct_chg"] or 0)))
        payload = {
            "tag": tag,
            "items": items,
            "unavailable": unavailable,
            "server_ts": _now_ms(),
        }
        with self._lock:
            self._boards_cache[tag] = (time.monotonic(), payload)
        return payload

    def _get_catalog(self, tag: str) -> List[Dict[str, Any]]:
        with self._lock:
            cached = self._catalog_cache.get(tag)
        if cached and time.monotonic() - cached[0] < CATALOG_FRESH_SECONDS:
            return cached[1]
        catalog = self.client.ths_index_catalog(tag=tag)
        if not catalog:
            raise FuyaoError("empty", f"同花顺指数目录为空（tag={tag}）")
        with self._lock:
            self._catalog_cache[tag] = (time.monotonic(), catalog)
        return catalog

    # ---- 板块成分股 ----

    def get_board_constituents(self, code: str) -> Dict[str, Any]:
        """板块成分股 + 实时行情富化（行情来自全市场快照帧，无额外请求）。

        快照帧取不到的成分股（停牌/新股/降级日无该股）行情字段为 null。
        """
        code = (code or "").strip().upper()
        if not code:
            raise ValueError("缺少板块代码")
        with self._lock:
            cached = self._constituents_cache.get(code)
        if cached and time.monotonic() - cached[0] < CONSTITUENTS_FRESH_SECONDS:
            payload = dict(cached[1])
            payload["cached"] = True
            return payload

        try:
            rows = self.client.ths_index_constituents(code)
        except FuyaoError as exc:
            stale = self._serve_stale(cached, CONSTITUENTS_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise

        quote_by_code = self._quote_frame_index()
        items = []
        for row in rows:
            ts_code = str(row.get("thscode") or "")
            quote = quote_by_code.get(ts_code) or {}
            items.append(
                {
                    "ts_code": ts_code,
                    "name": row.get("name") or quote.get("name"),
                    "last_price": quote.get("last_price"),
                    "pct_chg": quote.get("pct_chg"),
                    "amount_yuan": quote.get("amount_yuan"),
                }
            )
        payload = {"code": code, "total": len(items), "items": items}
        with self._lock:
            self._constituents_cache[code] = (time.monotonic(), payload)
        return payload

    @staticmethod
    def _quote_frame_index() -> Dict[str, Dict[str, Any]]:
        """全市场快照帧 → {ts_code: {last_price,pct_chg,amount_yuan,name}}。

        兼容扶摇快照（last_price/turnover 元）与降级本地日线
        （close/pre_close/amount 千元）两种 schema。
        """
        from app.services.market_snapshot_service import get_market_snapshot_service

        frame = get_market_snapshot_service().get_quote_frame()
        if frame is None or frame.empty:
            return {}
        index: Dict[str, Dict[str, Any]] = {}
        if "last_price" in frame.columns:
            records = frame.to_dict("records")
            for record in records:
                index[str(record.get("ts_code"))] = {
                    "name": record.get("name"),
                    "last_price": record.get("last_price"),
                    "pct_chg": record.get("pct_chg"),
                    "amount_yuan": record.get("turnover"),
                }
            return index
        # 本地日线 schema
        for record in frame.to_dict("records"):
            pre = record.get("pre_close")
            close = record.get("close")
            pct = (
                round((float(close) - float(pre)) / float(pre) * 100, 4)
                if pre and close and float(pre) != 0
                else None
            )
            index[str(record.get("ts_code"))] = {
                "name": record.get("name"),
                "last_price": close,
                "pct_chg": pct,
                "amount_yuan": (record.get("amount") or 0) * 1000.0,
            }
        return index

    # ---- 参数校验 ----

    @staticmethod
    def _validate_date(date: Optional[str]) -> Optional[str]:
        if date is None or str(date).strip() == "":
            return None
        text = str(date).strip()
        try:
            datetime.strptime(text, "%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"date 格式应为 YYYYMMDD，收到: {date}") from exc
        return text


_service: Optional[BoardMarketService] = None
_service_lock = threading.Lock()


def get_board_market_service() -> BoardMarketService:
    global _service
    with _service_lock:
        if _service is None:
            _service = BoardMarketService()
        return _service
