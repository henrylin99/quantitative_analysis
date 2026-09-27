"""基金数据服务（扶摇 /api/fund/*）。

职责：
- 端点聚合：业绩 = 最新净值 + 区间收益 + 最大回撤一次取齐
- 归一化：毫秒时间戳字段统一转 YYYYMMDD（北京时间零点口径，见 beijing_ms_to_ymd）
- 钳制：历史日线窗口 ≤5 自然年（服务端 1003），超长自动截断
- 缓存：进程内 TTL 缓存（资料/持仓分钟级，快照秒级）
- 客户端异常（FuyaoError）原样上抛，由 API 层统一转 HTTP 错误
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.utils.data_sources.fuyao_client import (
    BEIJING_TZ,
    FuyaoClient,
    beijing_ms_to_ymd,
)

PROFILE_CACHE_SECONDS = 600
SNAPSHOT_CACHE_SECONDS = 5
PERFORMANCE_CACHE_SECONDS = 600
HOLDINGS_CACHE_SECONDS = 3600
HISTORY_CACHE_SECONDS = 300
SEARCH_CACHE_SECONDS = 60
#: 服务端行情窗口上限（5 自然年），超长窗口本地截断避免 1003
FUND_WINDOW_MAX_DAYS = 5 * 365

#: 基金检索支持的 asset_type（/api/meta/tickers/search 实测）
FUND_ASSET_TYPES = ("fund-etf", "fund-lof", "fund-otc")

#: item 内需要毫秒时间戳 → YYYYMMDD 的字段
_DATE_MS_FIELDS = (
    "estab_date",
    "nav_date",
    "report_date_ms",
    "publish_date_ms",
    "start_date_ms",
    "end_date_ms",
    "modify_time_ms",
    "registration_date_ms",
    "ex_dividend_date_ms",
    "payment_date_ms",
    "reinvestment_date_ms",
    "profit_base_date_ms",
    "in_dividend_date_ms",
    "established_date_ms",
)


def ymd_to_ms(ymd: str) -> int:
    """YYYYMMDD（北京时间当日零点）→ epoch ms；格式非法抛 ValueError。"""
    try:
        dt = datetime.strptime(ymd.strip(), "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"日期格式须为 YYYYMMDD: {ymd!r}") from exc
    return int(dt.replace(tzinfo=BEIJING_TZ).timestamp() * 1000)


class FundService:
    """基金数据服务：进程内单例（get_fund_service），线程安全。"""

    def __init__(self, client: Optional[FuyaoClient] = None):
        self._client = client
        self._lock = threading.Lock()
        self._cache: Dict[Tuple, Tuple[float, Any]] = {}

    # ---- 基础 ----

    @property
    def client(self) -> FuyaoClient:
        if self._client is None:
            self._client = FuyaoClient()
        return self._client

    def _cached(self, key: Tuple, ttl_seconds: int, fetch):
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < ttl_seconds:
                return cached[1]
        value = fetch()
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
        return value

    @staticmethod
    def _convert_dates(payload: Any) -> Any:
        """递归把 *_ms / 已知日期字段毫秒值转 YYYYMMDD，追加 <field>_ymd。"""
        if isinstance(payload, list):
            return [FundService._convert_dates(row) for row in payload]
        if not isinstance(payload, dict):
            return payload
        row = dict(payload)
        for field in _DATE_MS_FIELDS:
            value = row.get(field)
            ymd = beijing_ms_to_ymd(value) if isinstance(value, (int, float)) else None
            if ymd:
                row[f"{field}_ymd"] = ymd
        return row

    @staticmethod
    def _first_item(data: Any) -> Dict[str, Any]:
        """取单条记录：客户端方法已解包 item[] 列表，returns/drawdowns 等仍是信封 dict。"""
        if isinstance(data, dict):
            items = data.get("item") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return items[0] if items else {}

    # ---- 基金检索（列表页） ----

    def search_funds(
        self, query: str, asset_type: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """基金检索（名称/代码模糊匹配，用于基金列表页）。

        asset_type 可选 fund-etf / fund-lof / fund-otc；缺省时上游返回混合
        结果（含股票/指数），这里过滤只保留基金行。
        """
        rows = self._cached(
            ("search", query, asset_type, limit),
            SEARCH_CACHE_SECONDS,
            lambda: self.client.ticker_search(query, asset_type=asset_type, limit=limit),
        )
        return [row for row in rows if str(row.get("asset_type") or "").startswith("fund")]

    # ---- T1：资料 / 行情 / 业绩 / 持仓 ----

    def get_profile(self, thscode: str) -> Dict[str, Any]:
        """基金基本资料（成立日期、管理人、经理、规模、单位净值等）。"""
        return self._cached(
            ("profile", thscode),
            PROFILE_CACHE_SECONDS,
            lambda: self._convert_dates(self._first_item(self.client.fund_profile(thscode))),
        )

    def get_snapshot(self, thscode: str) -> Dict[str, Any]:
        """场内基金实时快照（仅 ETF/LOF）。"""
        return self._cached(
            ("snapshot", thscode),
            SNAPSHOT_CACHE_SECONDS,
            lambda: self._first_item(self.client.fund_market_snapshot(thscode)),
        )

    def get_history(
        self, thscode: str, start: str, end: str
    ) -> Dict[str, Any]:
        """ETF 前复权历史日线（start/end 为 YYYYMMDD；窗口超 5 年自动截断保留近端）。

        返回 {thscode, start, end, items}，items 按日期升序，date 字段为 YYYYMMDD。
        """
        end_ms = ymd_to_ms(end)
        start_ms = ymd_to_ms(start)
        if start_ms > end_ms:
            raise ValueError(f"start 不能晚于 end: {start} > {end}")
        max_window_ms = FUND_WINDOW_MAX_DAYS * 86400 * 1000
        if end_ms - start_ms > max_window_ms:
            clamped = end_ms - max_window_ms
            logger.info(f"[fund] 窗口超 {FUND_WINDOW_MAX_DAYS} 天，截断 {start} → {beijing_ms_to_ymd(clamped)}")
            start_ms = clamped
        items = self._cached(
            ("history", thscode, start_ms, end_ms),
            HISTORY_CACHE_SECONDS,
            lambda: self.client.fund_historical(thscode, start_ms=start_ms, end_ms=end_ms),
        )
        rows = []
        for row in items:
            converted = dict(row)
            ymd = beijing_ms_to_ymd(converted.get("date_ms"))
            if ymd:
                converted["date"] = ymd
            rows.append(converted)
        return {"thscode": thscode, "start": start, "end": end, "items": rows}

    def get_nav_series(self, thscode: str, range: str = "year", nav_type: str = "unit,adj") -> List[Dict[str, Any]]:
        """净值序列（range: week/month/tmonth/hyear/year/twoyear/tyear/fyear，缺省仅最新一条）。"""
        return self._cached(
            ("nav_series", thscode, range, nav_type),
            PERFORMANCE_CACHE_SECONDS,
            lambda: self._convert_dates(self.client.fund_nav(thscode, range=range, nav_type=nav_type)),
        )

    def get_performance(self, thscode: str) -> Dict[str, Any]:
        """业绩聚合：最新净值 + 区间收益（含同类排名）+ 各区间最大回撤。"""
        def fetch() -> Dict[str, Any]:
            nav_items = self.client.fund_nav(thscode)
            returns = self._first_item(self.client.fund_returns(thscode))
            drawdowns = self._first_item(self.client.fund_drawdowns(thscode))
            return {
                "thscode": thscode,
                "nav_latest": self._convert_dates(nav_items[-1]) if nav_items else {},
                "returns": returns,
                "drawdowns": drawdowns,
            }

        return self._cached(("performance", thscode), PERFORMANCE_CACHE_SECONDS, fetch)

    def get_holdings(self, thscode: str) -> Dict[str, Any]:
        """最新重仓持仓：顶层汇总（股票/债券/基金占比、集中度）+ 明细（日期已转 YYYYMMDD）。"""
        data = self._cached(
            ("holdings", thscode),
            HOLDINGS_CACHE_SECONDS,
            lambda: self.client.fund_holdings(thscode),
        )
        return {
            "thscode": thscode,
            "summary": {
                k: v
                for k, v in data.items()
                if k not in ("item", "timestamp")
            },
            "items": self._convert_dates(data.get("item") or []),
        }

    # ---- T2：持有人 / 配置 / 经理 / 诊断 / 分红 / 公司 ----

    def get_holders(self, thscode: str) -> Dict[str, Any]:
        """持有人结构（机构/个人占比、户数）+ 前十大持有人。

        holders/top 实测会返回多期记录，这里只保留最新报告期前 10 条。
        """
        def fetch() -> Dict[str, Any]:
            structure = self.client.fund_holders_detail(thscode)
            top = self.client.fund_holders_top(thscode)
            if top:
                latest = max((row.get("report_date_ms") or 0) for row in top)
                top = [row for row in top if (row.get("report_date_ms") or 0) == latest][:10]
            return {
                "thscode": thscode,
                "structure": self._convert_dates(structure),
                "top": self._convert_dates(top),
            }

        return self._cached(("holders", thscode), HOLDINGS_CACHE_SECONDS, fetch)

    def get_asset_allocation(self, thscode: str) -> List[Dict[str, Any]]:
        """历史资产配置（报告期股票/债券/存款/其他占比）。"""
        return self._cached(
            ("asset_allocation", thscode),
            HOLDINGS_CACHE_SECONDS,
            lambda: self._convert_dates(self.client.fund_asset_allocation(thscode)),
        )

    def get_industry_allocation(self, thscode: str) -> List[Dict[str, Any]]:
        """历史行业配置（report_period 如 2026Q2）。"""
        return self._cached(
            ("industry_allocation", thscode),
            HOLDINGS_CACHE_SECONDS,
            lambda: self.client.fund_industry_allocation(thscode),
        )

    def get_manager(self, manager_id: str) -> Dict[str, Any]:
        """基金经理详情（manager_id 来自基金基本资料 manager_info）。"""
        return self._cached(
            ("manager", manager_id),
            PROFILE_CACHE_SECONDS,
            lambda: self._first_item(self.client.fund_manager_detail(manager_id)),
        )

    def get_diagnostics(self, thscode: str) -> Dict[str, Any]:
        """基金诊断详情（维度/同类对比/韧性，上游结构透传）。"""
        return self._cached(
            ("diagnostics", thscode),
            PROFILE_CACHE_SECONDS,
            lambda: self._first_item(self.client.fund_diagnostics(thscode)),
        )

    def get_dividends(self, thscode: str) -> Dict[str, Any]:
        """历史分红记录（日期已转 YYYYMMDD）。"""
        data = self._cached(
            ("dividends", thscode),
            PROFILE_CACHE_SECONDS,
            lambda: self.client.fund_dividends(thscode),
        )
        return {
            "thscode": thscode,
            "dividend_count": data.get("dividend_count"),
            "dividend_total": data.get("dividend_total"),
            "items": self._convert_dates(data.get("item") or []),
        }

    def get_company(self, company_id: str) -> Dict[str, Any]:
        """基金公司详情（company_id 来自基金基本资料）。"""
        return self._cached(
            ("company", company_id),
            PROFILE_CACHE_SECONDS,
            lambda: self._first_item(self.client.fund_company(company_id)),
        )


_service: Optional[FundService] = None
_service_lock = threading.Lock()


def get_fund_service() -> FundService:
    """进程内单例访问器。"""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = FundService()
    return _service
