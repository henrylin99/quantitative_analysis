"""板块与连板分析服务：涨停池 / 连板天梯 / 同花顺行业·概念板块。

数据全部来自扶摇特色数据域：
- 涨停池 ``limit-up-pool``：按交易日的涨停个股（连板数/封单额/涨停时间/原因）
- 连板天梯 ``limit-up-ladder``：近 30 个交易日的 2 板~7 板+ 矩阵
- 同花顺指数目录+快照：行业（320 个）/概念（390 个）板块的实时涨跌排行
- 指数成分股：板块成分清单，用全市场快照帧富化个股行情
- 历史热股 ``hot-stock-list-history`` / 排名走势 ``hot-stock-rank-trend``
- 个股异动原因 ``anomaly-analysis-list`` / ``anomaly-analysis-stock``（当日）

缓存策略：
- 涨停池按（日期,页）缓存，盘中 60s、历史日永久（当日数据不再变化）
- 天梯/板块快照分别 5 分钟 / 60 秒；目录与成分股按小时~天缓存
- 历史热股/排名走势同池口径（历史日永久、当日 5 分钟）；异动原因 60s
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
from app.utils.data_sources.fuyao_client import (
    ANOMALY_BATCH_LIMIT,
    BATCH_LIMIT,
    BEIJING_TZ,
    FuyaoClient,
    FuyaoError,
    beijing_ms_to_ymd,
)

POOL_FRESH_SECONDS = 60.0
LADDER_FRESH_SECONDS = 300.0
BOARD_SNAPSHOT_FRESH_SECONDS = 60.0
CATALOG_FRESH_SECONDS = 6 * 3600.0
CONSTITUENTS_FRESH_SECONDS = 3600.0
TRADING_DAYS_FRESH_SECONDS = 6 * 3600.0
HOT_FRESH_SECONDS = 300.0
SEARCH_FRESH_SECONDS = 60.0
STALE_SERVE_SECONDS = 3600.0
ANOMALY_FRESH_SECONDS = 60.0
AUCTION_SNAPSHOT_FRESH_SECONDS = 30.0
OPPORTUNITY_FRESH_SECONDS = 60.0
OPPORTUNITY_DATES_FRESH_SECONDS = 600.0
ABNORMAL_FRESH_SECONDS = 600.0
#: 进程内缓存容量上限（按日期/检索词等键会随使用增长，防无界）
POOL_CACHE_MAX_ENTRIES = 64
SEARCH_CACHE_MAX_ENTRIES = 128
CONSTITUENTS_CACHE_MAX_ENTRIES = 128

#: 集合竞价机会筛选的 market 取值（扶摇 auction-stock-opportunities）
AUCTION_MARKETS = ("a_share", "sh_sz_main", "sh_a", "sz_a", "gem", "star")

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

#: 个股异动原因合法标签（扶摇 anomaly-analysis tag_codes）
ANOMALY_VALID_TAGS = (
    "LIMIT_UP",
    "LIMIT_DOWN",
    "SHARP_RISE",
    "SHARP_FALL",
    "RAPID_RALLY",
    "RAPID_DECLINE",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ymd_to_beijing_ms(ymd: str) -> int:
    """YYYYMMDD → 北京时间当日零点 epoch ms（扶摇 date_ms 口径）。"""
    dt = datetime.strptime(str(ymd), "%Y%m%d").replace(tzinfo=BEIJING_TZ)
    return int(dt.timestamp() * 1000)


def _ymd_to_iso(ymd: str) -> str:
    """YYYYMMDD → yyyy-MM-dd（历史热股/排名走势接口的日期口径）。"""
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


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
        self._hot_history_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._rank_trend_cache: Dict[Tuple[str, str, str], Tuple[float, Dict[str, Any]]] = {}
        self._anomaly_cache: Dict[Tuple[str, ...], Tuple[float, Dict[str, Any]]] = {}
        self._auction_snapshot_cache: Dict[
            Tuple[Tuple[str, ...], str], Tuple[float, Dict[str, Any]]
        ] = {}
        self._opportunity_cache: Dict[Tuple[str, ...], Tuple[float, Dict[str, Any]]] = {}
        self._opportunity_dates_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._abnormal_cache: Dict[Tuple[str, int, int], Tuple[float, Dict[str, Any]]] = {}
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

    # ---- 历史热股排行 / 个股排名走势 / 个股异动原因 ----

    def get_hot_stock_history(self, date: Optional[str] = None) -> Dict[str, Any]:
        """历史热股排行（date YYYYMMDD 可空=最近交易日；历史日缓存视为永久）。"""
        resolved = self._validate_date(date) or self.latest_trade_date()
        with self._lock:
            cached = self._hot_history_cache.get(resolved)
        fresh = self._pool_fresh_seconds(resolved)
        if cached and time.monotonic() - cached[0] < fresh:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            data = self.client.hot_stock_list_history(_ymd_to_iso(resolved))
        except FuyaoError as exc:
            stale = self._serve_stale(cached, fresh, exc)
            if stale is not None:
                return stale
            raise

        payload = {
            "date": resolved,
            "items": [
                {
                    "ts_code": row.get("thscode"),
                    "ticker": row.get("ticker"),
                    "name": row.get("name"),
                    "rank": row.get("rank"),
                }
                for row in data.get("item") or []
            ],
        }
        with self._lock:
            evict_oldest(self._hot_history_cache, POOL_CACHE_MAX_ENTRIES)
            self._hot_history_cache[resolved] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    def get_hot_stock_rank_trend(self, ts_code: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """个股热榜排名走势（YYYYMMDD 窗口 ≤1 年；start>end 前置校验）。"""
        code = (ts_code or "").strip().upper()
        if not code:
            raise ValueError("缺少 ts_code 参数")
        start = self._validate_date(start_date)
        end = self._validate_date(end_date)
        if not start or not end:
            raise ValueError("start_date/end_date 均必填（YYYYMMDD）")
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        key = (code, start, end)
        with self._lock:
            cached = self._rank_trend_cache.get(key)
        # 窗口终点已是历史日 → 数据不再变化，缓存视为永久
        fresh = self._pool_fresh_seconds(end)
        if cached and time.monotonic() - cached[0] < fresh:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            rows = self.client.hot_stock_rank_trend(code, _ymd_to_iso(start), _ymd_to_iso(end))
        except FuyaoError as exc:
            stale = self._serve_stale(cached, fresh, exc)
            if stale is not None:
                return stale
            raise

        payload = {
            "ts_code": code,
            "start_date": start,
            "end_date": end,
            "points": [
                {
                    "date": row.get("date"),
                    "date_ms": row.get("date_ms"),
                    "rank": row.get("rank"),
                }
                for row in rows
            ],
        }
        with self._lock:
            evict_oldest(self._rank_trend_cache, POOL_CACHE_MAX_ENTRIES)
            self._rank_trend_cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    def get_anomaly_analysis(self, tag_codes: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """当日个股异动原因（tags 可选多值 OR；大小写不敏感，缓存 60s）。"""
        tags = tuple(
            dict.fromkeys(
                str(tag).strip().upper() for tag in (tag_codes or []) if str(tag).strip()
            )
        )
        unknown = [tag for tag in tags if tag not in ANOMALY_VALID_TAGS]
        if unknown:
            raise ValueError(
                f"tags 含非法值: {','.join(unknown)}（合法值: {'/'.join(ANOMALY_VALID_TAGS)}）"
            )
        with self._lock:
            cached = self._anomaly_cache.get(tags)
        if cached and time.monotonic() - cached[0] < ANOMALY_FRESH_SECONDS:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            rows = self.client.anomaly_analysis_list(list(tags) or None)
        except FuyaoError as exc:
            stale = self._serve_stale(cached, ANOMALY_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise

        payload = {
            "tags": list(tags),
            "items": self._normalize_anomaly_items(rows),
            "server_ts": _now_ms(),
        }
        with self._lock:
            evict_oldest(self._anomaly_cache, POOL_CACHE_MAX_ENTRIES)
            self._anomaly_cache[tags] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    def get_anomaly_analysis_by_stocks(self, codes: Sequence[str]) -> Dict[str, Any]:
        """按代码批量查询当日个股异动原因（去重前 ≤50 只，缓存 60s）。"""
        cleaned = [str(code).strip().upper() for code in codes if str(code).strip()]
        if not cleaned:
            raise ValueError("缺少 codes 参数")
        if len(cleaned) > ANOMALY_BATCH_LIMIT:
            raise ValueError(f"codes 单次最多 {ANOMALY_BATCH_LIMIT} 只")
        key = tuple(dict.fromkeys(cleaned))
        with self._lock:
            cached = self._anomaly_cache.get(key)
        if cached and time.monotonic() - cached[0] < ANOMALY_FRESH_SECONDS:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            rows = self.client.anomaly_analysis_stock(list(key))
        except FuyaoError as exc:
            stale = self._serve_stale(cached, ANOMALY_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise

        payload = {
            "codes": list(key),
            "items": self._normalize_anomaly_items(rows),
            "server_ts": _now_ms(),
        }
        with self._lock:
            evict_oldest(self._anomaly_cache, POOL_CACHE_MAX_ENTRIES)
            self._anomaly_cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    @staticmethod
    def _normalize_anomaly_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "ts_code": row.get("thscode"),
                "name": row.get("stock_name"),
                "tag": row.get("tag_name"),
                "content": row.get("analysis_content"),
                "keywords": row.get("keyword_list") or [],
            }
            for row in items
        ]

    # ---- 集合竞价 / 异动股票监控 ----

    def get_auction_snapshot(
        self, codes: Sequence[str], stage: Optional[str] = None
    ) -> Dict[str, Any]:
        """集合竞价快照（codes ≤100，stage live/final 可空；缓存 30s）。"""
        cleaned = [str(code).strip().upper() for code in codes if str(code).strip()]
        if not cleaned:
            raise ValueError("缺少 codes 参数")
        if len(cleaned) > BATCH_LIMIT:
            raise ValueError(f"codes 单次最多 {BATCH_LIMIT} 只")
        # 文档写 finallive，实测上游合法值为 live/final
        if stage not in (None, "", "live", "final"):
            raise ValueError("stage 取值须为 live/final")
        stage_key = stage or ""
        key = (tuple(dict.fromkeys(cleaned)), stage_key)
        with self._lock:
            cached = self._auction_snapshot_cache.get(key)
        if cached and time.monotonic() - cached[0] < AUCTION_SNAPSHOT_FRESH_SECONDS:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            data = self.client.auction_snapshot(list(key[0]), stage=stage or None)
        except FuyaoError as exc:
            stale = self._serve_stale(cached, AUCTION_SNAPSHOT_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise

        payload = {
            "codes": list(key[0]),
            "stage": stage or None,
            "auction_phase": data.get("auction_phase"),
            "data_status": data.get("data_status"),
            "items": [self._normalize_auction_item(row) for row in data.get("item") or []],
            "server_ts": data.get("timestamp") or _now_ms(),
        }
        with self._lock:
            evict_oldest(self._auction_snapshot_cache, POOL_CACHE_MAX_ENTRIES)
            self._auction_snapshot_cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    @staticmethod
    def _normalize_auction_item(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ts_code": row.get("thscode"),
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "auction_price": row.get("auction_price"),
            "auction_pct": row.get("auction_pct"),
            "auction_volume": row.get("auction_volume"),
            "auction_amount": row.get("auction_amount"),
            "auction_unmatched": row.get("auction_unmatched"),
            "auction_turnover_pct": row.get("auction_turnover_pct"),
            "auction_yesterday_ratio_pct": row.get("auction_yesterday_ratio_pct"),
            "auction_volume_ratio": row.get("auction_volume_ratio"),
            "pre_close_price": row.get("pre_close_price"),
            "open_price": row.get("open_price"),
            "last_price": row.get("last_price"),
            "float_market_cap": row.get("float_market_cap"),
        }

    def get_auction_opportunities(
        self,
        date: Optional[str] = None,
        warn_types: Optional[Sequence[str]] = None,
        market: Optional[str] = None,
        exclude_st: bool = False,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> Dict[str, Any]:
        """集合竞价个股机会筛选（date YYYYMMDD 可空=当日实时；size 1~20）。

        历史日数据不再变化，缓存视为永久；当日缓存 60s。
        """
        resolved = self._validate_date(date)
        if market and market not in AUCTION_MARKETS:
            raise ValueError(f"market 取值须为 {'/'.join(AUCTION_MARKETS)}")
        size = min(max(int(size), 1), 20)
        page = max(int(page), 1)
        if sort_by not in (None, "", "warn_time", "warn_type"):
            raise ValueError("sort_by 取值须为 warn_time/warn_type")
        if sort_order not in (None, "", "asc", "desc"):
            raise ValueError("sort_order 取值须为 asc/desc")
        warn_key = tuple(
            dict.fromkeys(str(w).strip() for w in (warn_types or []) if str(w).strip())
        )
        key = (
            resolved or "",
            warn_key,
            market or "",
            bool(exclude_st),
            sort_by or "",
            sort_order or "",
            page,
            size,
        )
        with self._lock:
            cached = self._opportunity_cache.get(key)
        fresh = self._pool_fresh_seconds(resolved or self._today())
        if cached and time.monotonic() - cached[0] < fresh:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            data = self.client.auction_stock_opportunities(
                date=_ymd_to_iso(resolved) if resolved else None,
                warn_types=list(warn_key) or None,
                market=market or None,
                exclude_st=bool(exclude_st) or None,
                sort_by=sort_by or None,
                sort_order=sort_order or None,
                page=page,
                size=size,
            )
        except FuyaoError as exc:
            stale = self._serve_stale(cached, fresh, exc)
            if stale is not None:
                return stale
            raise

        pagination = data.get("pagination") or {}
        trade_date = str(data.get("trade_date") or "").replace("-", "")
        payload = {
            "date": resolved or trade_date or None,
            "mode": data.get("mode"),
            "total": int(pagination.get("total") or len(data.get("item") or [])),
            "page": page,
            "size": size,
            "has_next": bool(pagination.get("has_next")),
            "items": [
                self._normalize_opportunity_item(row) for row in data.get("item") or []
            ],
            "server_ts": data.get("timestamp") or _now_ms(),
        }
        with self._lock:
            evict_oldest(self._opportunity_cache, POOL_CACHE_MAX_ENTRIES)
            self._opportunity_cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    @staticmethod
    def _normalize_opportunity_item(row: Dict[str, Any]) -> Dict[str, Any]:
        warn_ts = row.get("warn_timestamp")
        try:
            warn_time = (
                datetime.fromtimestamp(float(warn_ts) / 1000.0, tz=BEIJING_TZ).strftime("%H:%M:%S")
                if warn_ts is not None
                else None
            )
        except (OverflowError, OSError, ValueError):
            warn_time = None
        ratio = row.get("bid_change_ratio")
        return {
            "ts_code": row.get("thscode"),
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "warn_type": row.get("warn_type"),
            "warn_name": row.get("warn_name"),
            "warn_time": warn_time,
            "bid_price": row.get("bid_price"),
            # 扶摇 bid_change_ratio 为小数比例，统一转百分数原值展示
            "bid_pct": round(float(ratio) * 100, 2) if isinstance(ratio, (int, float)) else None,
            "bid_amount": row.get("bid_amount"),
            "previous_amount": row.get("previous_amount"),
            "explain": row.get("explain"),
            "grade": row.get("grade"),
            "related_block": row.get("related_block"),
        }

    def get_auction_opportunity_dates(self) -> Dict[str, Any]:
        """集合竞价可选交易日期（YYYYMMDD 升序 + latest_date；缓存 10 分钟）。"""
        with self._lock:
            cached = self._opportunity_dates_cache
        if cached and time.monotonic() - cached[0] < OPPORTUNITY_DATES_FRESH_SECONDS:
            return copy.deepcopy(cached[1])
        try:
            data = self.client.auction_opportunity_dates()
        except FuyaoError as exc:
            stale = self._serve_stale(cached, OPPORTUNITY_DATES_FRESH_SECONDS, exc)
            if stale is not None:
                return stale
            raise

        latest = str(data.get("latest_date") or "").replace("-", "") or None
        payload = {
            "dates": [
                str(d).replace("-", "")
                for d in (data.get("dates") or [])
                if str(d).strip()
            ],
            "latest_date": latest,
            "server_ts": data.get("timestamp") or _now_ms(),
        }
        with self._lock:
            self._opportunity_dates_cache = (time.monotonic(), copy.deepcopy(payload))
        return payload

    def get_abnormal_monitor(self, state: str = "current", page: int = 1, size: int = 30) -> Dict[str, Any]:
        """异动股票监控名单（state current/history；当日缓存 10 分钟，历史永久）。"""
        if state not in ("current", "history"):
            raise ValueError("state 取值须为 current/history")
        size = min(max(int(size), 1), 30)
        page = max(int(page), 1)
        key = (state, page, size)
        with self._lock:
            cached = self._abnormal_cache.get(key)
        fresh = ABNORMAL_FRESH_SECONDS if state == "current" else 24 * 3600.0
        if cached and time.monotonic() - cached[0] < fresh:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            data = self.client.abnormal_monitor_list(state=state, page=page, size=size)
        except FuyaoError as exc:
            stale = self._serve_stale(cached, fresh, exc)
            if stale is not None:
                return stale
            raise

        pagination = data.get("pagination") or {}
        payload = {
            "state": state,
            "page": page,
            "size": size,
            "total": int(pagination.get("total") or len(data.get("item") or [])),
            "has_next": bool(pagination.get("has_next")),
            "items": [self._normalize_abnormal_item(row) for row in data.get("item") or []],
            "server_ts": _now_ms(),
        }
        with self._lock:
            evict_oldest(self._abnormal_cache, POOL_CACHE_MAX_ENTRIES)
            self._abnormal_cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    @staticmethod
    def _normalize_abnormal_item(row: Dict[str, Any]) -> Dict[str, Any]:
        # 实测 monitor_label 直接返回「严重异动/重点监控」文案（文档为 1/2 码口径），两者都兼容
        label = str(row.get("monitor_label") or "")
        return {
            "ts_code": row.get("thscode"),
            "name": row.get("name"),
            "start_date": beijing_ms_to_ymd(row.get("start_date_ms")),
            "end_date": beijing_ms_to_ymd(row.get("end_date_ms")),
            "monitor_type": row.get("monitor_type"),
            "severe": "严重" in label or label in ("1", "2"),
            "monitor_label": row.get("monitor_label"),
        }

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
