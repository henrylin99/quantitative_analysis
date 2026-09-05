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

import copy
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.services.market_snapshot_service import evict_oldest
from app.utils.data_sources.fuyao_client import BEIJING_TZ, FuyaoClient, FuyaoError

POOL_FRESH_SECONDS = 60.0
LADDER_FRESH_SECONDS = 300.0
BOARD_SNAPSHOT_FRESH_SECONDS = 60.0
CATALOG_FRESH_SECONDS = 6 * 3600.0
CONSTITUENTS_FRESH_SECONDS = 3600.0
TRADING_DAYS_FRESH_SECONDS = 6 * 3600.0
HOT_FRESH_SECONDS = 300.0
SEARCH_FRESH_SECONDS = 60.0
STALE_SERVE_SECONDS = 3600.0
#: 进程内缓存容量上限（按日期/检索词等键会随使用增长，防无界）
POOL_CACHE_MAX_ENTRIES = 64
SEARCH_CACHE_MAX_ENTRIES = 128
CONSTITUENTS_CACHE_MAX_ENTRIES = 128

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
        self._down_pool_cache: Dict[Tuple[str, int, int], Tuple[float, Dict[str, Any]]] = {}
        self._break_pool_cache: Dict[Tuple[str, int, int], Tuple[float, Dict[str, Any]]] = {}
        self._hot_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._search_cache: Dict[Tuple[str, int], Tuple[float, Dict[str, Any]]] = {}
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
        """新鲜期过期后 1 小时内回供旧值（标 stale），超出窗口返回 None。

        回供的是深拷贝：调用方可能就地改 payload（如覆盖 cached/stale 标记），
        不能与缓存共享嵌套结构。
        """
        if cached and time.monotonic() - cached[0] < fresh_seconds + STALE_SERVE_SECONDS:
            logger.warning(f"[board] 扶摇拉取失败，回供过期缓存: {exc}")
            payload = copy.deepcopy(cached[1])
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

    # ---- 涨停 / 跌停 / 炸板池 ----

    def _get_special_pool(
        self,
        cache: Dict[Tuple[str, int, int], Tuple[float, Dict[str, Any]]],
        fetch,
        normalize,
        date: Optional[str],
        page: int,
        size: int,
    ) -> Dict[str, Any]:
        """特色数据池通用获取：日期解析 + TTL 缓存 + 过期回供。

        fetch(date_ms, page, size) 返回 {pagination, item}；normalize 把
        服务端字段映射为前端蛇形字段。历史日数据不再变化，缓存视为永久。
        """
        resolved = self._validate_date(date) or self.latest_trade_date()
        key = (resolved, page, min(int(size), 200))
        with self._lock:
            cached = cache.get(key)
        fresh = self._pool_fresh_seconds(resolved)
        if cached and time.monotonic() - cached[0] < fresh:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            data = fetch(_ymd_to_beijing_ms(resolved), key[1], key[2])
            pagination = data.get("pagination") or {}
            payload = {
                "date": resolved,
                "total": int(pagination.get("total") or len(data.get("item") or [])),
                "page": key[1],
                "size": key[2],
                "items": normalize(data.get("item") or []),
            }
            with self._lock:
                evict_oldest(cache, POOL_CACHE_MAX_ENTRIES)
                # 写入侧深拷贝：缓存对象与首次返回给调用方的对象隔离
                cache[key] = (time.monotonic(), copy.deepcopy(payload))
            return payload
        except FuyaoError as exc:
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
        """涨停池字段重命名为前端友好蛇形（原始含义见 client docstring）。"""
        return [
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
            for row in items
        ]

    @staticmethod
    def _normalize_down_pool_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "ts_code": row.get("thscode"),
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "last_price": row.get("last_price"),
                "pct_chg": row.get("price_change_ratio_pct"),
                "first_limit_time": row.get("first_limit_time"),
                "last_limit_time": row.get("last_limit_time"),
                "turnover_ratio_pct": row.get("turnover_ratio_pct"),
            }
            for row in items
        ]

    @staticmethod
    def _normalize_break_pool_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "ts_code": row.get("thscode"),
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "last_price": row.get("last_price"),
                "pct_chg": row.get("price_change_ratio_pct"),
                "open_times": row.get("open_times"),
                "turnover_ratio_pct": row.get("turnover_ratio_pct"),
                "turnover": row.get("turnover"),
            }
            for row in items
        ]

    def get_limit_up_pool(self, date: Optional[str] = None, page: int = 1, size: int = 100) -> Dict[str, Any]:
        """涨停池（date YYYYMMDD 可空=最近交易日；连板数降序）。"""
        return self._get_special_pool(
            self._pool_cache,
            lambda ms, p, s: self.client.limit_up_pool(date_ms=ms, page=p, size=s),
            self._normalize_pool_items,
            date,
            page,
            size,
        )

    def get_limit_down_pool(self, date: Optional[str] = None, page: int = 1, size: int = 100) -> Dict[str, Any]:
        """跌停池（date 口径同涨停池）。"""
        return self._get_special_pool(
            self._down_pool_cache,
            lambda ms, p, s: self.client.limit_down_pool(date_ms=ms, page=p, size=s),
            self._normalize_down_pool_items,
            date,
            page,
            size,
        )

    def get_limit_break_pool(self, date: Optional[str] = None, page: int = 1, size: int = 100) -> Dict[str, Any]:
        """炸板池（曾涨停后开板；date 口径同涨停池）。"""
        return self._get_special_pool(
            self._break_pool_cache,
            lambda ms, p, s: self.client.limit_break_pool(date_ms=ms, page=p, size=s),
            self._normalize_break_pool_items,
            date,
            page,
            size,
        )

    def get_limit_up_ladder(self) -> Dict[str, Any]:
        """连板天梯：30 个交易日的 {date, counts:{连板数:家数}, highest}。"""
        with self._lock:
            cached = self._ladder_cache
        if cached and time.monotonic() - cached[0] < LADDER_FRESH_SECONDS:
            return copy.deepcopy(cached[1])
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
            self._ladder_cache = (time.monotonic(), copy.deepcopy(payload))
        return payload

    # ---- 同花顺热股榜 / 飙升榜 ----

    def get_hot_stocks(self, period: str = "day") -> Dict[str, Any]:
        """热股榜 + 飙升榜（period: day/hour；缓存 5 分钟）。

        heat 为字符串数值，统一转 float 便于前端排序展示。
        """
        if period not in ("day", "hour"):
            raise ValueError("period 取值须为 day/hour")
        with self._lock:
            cached = self._hot_cache.get(period)
        if cached and time.monotonic() - cached[0] < HOT_FRESH_SECONDS:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            hot = self._normalize_hot_items(self.client.hot_stock_list(period=period))
            skyrocket = self._normalize_hot_items(self.client.skyrocket_list(period=period))
            payload = {"period": period, "hot": hot, "skyrocket": skyrocket}
        except FuyaoError as exc:
            stale = self._serve_stale(cached, HOT_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise

        with self._lock:
            self._hot_cache[period] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    @staticmethod
    def _normalize_hot_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in items:
            try:
                heat = float(row.get("heat"))
            except (TypeError, ValueError):
                heat = None
            normalized.append(
                {
                    "ts_code": row.get("thscode"),
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "rank": row.get("rank"),
                    "heat": heat,
                    "rank_change": row.get("rank_change"),
                    "rank_trend": row.get("rank_trend"),
                }
            )
        return normalized

    # ---- 标的检索 ----

    def search_tickers(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """名称/代码模糊检索（自选添加联想；透传扶摇，短缓存 60s）。"""
        text = (query or "").strip()
        if len(text) < 2:
            raise ValueError("检索关键字至少 2 个字符")
        key = (text.lower(), min(int(limit), 20))
        with self._lock:
            cached = self._search_cache.get(key)
        if cached and time.monotonic() - cached[0] < SEARCH_FRESH_SECONDS:
            return copy.deepcopy(cached[1])
        rows = self.client.ticker_search(text, asset_type="a-share", limit=key[1])
        payload = {
            "query": text,
            "items": [
                {
                    "ts_code": row.get("thscode"),
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "exchange": row.get("exchange"),
                }
                for row in rows
            ],
        }
        with self._lock:
            evict_oldest(self._search_cache, SEARCH_CACHE_MAX_ENTRIES)
            self._search_cache[key] = (time.monotonic(), copy.deepcopy(payload))
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
            payload = copy.deepcopy(cached[1])
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
            self._boards_cache[tag] = (time.monotonic(), copy.deepcopy(payload))
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
            payload = copy.deepcopy(cached[1])
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
            evict_oldest(self._constituents_cache, CONSTITUENTS_CACHE_MAX_ENTRIES)
            self._constituents_cache[code] = (time.monotonic(), copy.deepcopy(payload))
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
