"""TickFlow 轻量 REST 客户端（free 档兜底/校验源）。

端点契约参考 tick-stock-panel 项目（MIT License, Copyright (c) 2026
tickflow-stock-panel contributors）及其封装的官方 SDK。本项目不引入
``tickflow[all]`` SDK（依赖过重），这里只封装 free 档用得到的两个 GET 接口。

契约要点：
- 认证：请求头 ``x-api-key``（注意与扶摇的 X-api-key 大小写不同，
  HTTP 头本身不区分大小写，这里遵循各服务方的惯例拼写）
- 端点：``https://api.tickflow.org``（免费档 key 也走付费端点，
  free-api 忽略 key；tick-stock-panel 的探测逻辑即以此为准）
- 档位：日K 全档可用；除权因子 starter+；分钟K pro+。
  free 档 key 的限速约 5 rpm（单标的日K），
  **不得用于全市场批量任务**——那是 tushare/fuyao job 的职责
- 时间：K线响应 timestamp 数组为北京时间零点的 epoch ms

不可用权限返回 HTTP 403 + ``{"code": "NO_XXX_PERMISSION"}``，
本客户端原样抛 TickflowError(code=...)，由 detect_tier 据此判档。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.tickflow.org"
API_KEY_ENV = "TICKFLOW_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 30


class TickflowError(RuntimeError):
    """TickFlow 业务错误（权限不足/参数错误/网络异常）。"""

    def __init__(self, code: Any, message: str):
        super().__init__(f"tickflow error code={code}: {message}")
        self.code = code
        self.message = message

    @property
    def is_permission_denied(self) -> bool:
        text = f"{self.code} {self.message}"
        return "PERMISSION" in text or "权限" in text


class TickflowClient:
    """TickFlow REST 客户端：日K / 实时行情 / 档位探测。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: Optional[requests.Session] = None,
    ):
        # 与 db_utils 一致：脚本直接运行/被 API 调用时都先加载 .env
        load_dotenv()
        self.api_key = (api_key if api_key is not None else os.getenv(API_KEY_ENV, "")).strip()
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.api_key:
            raise TickflowError("no_key", f"未配置 {API_KEY_ENV}，请在 .env 中设置后重试")
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self._session.get(
                f"{self.base_url}{path}",
                headers={"x-api-key": self.api_key},
                params=clean_params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TickflowError("network", f"tickflow 请求失败: {exc}") from exc
        if resp.status_code != 200:
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            raise TickflowError(
                payload.get("code", resp.status_code),
                payload.get("message", resp.text[:200]),
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise TickflowError("bad_json", f"tickflow 响应不是 JSON: {resp.text[:200]}") from exc
        return payload.get("data")

    def klines(
        self,
        symbol: str,
        period: str = "1d",
        count: Optional[int] = None,
        adjust: str = "none",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, List[Any]]:
        """单标的K线（列数组紧凑格式）。返回含 timestamp/open/high/low/close/volume/amount。"""
        data = self._get(
            "/v1/klines",
            {
                "symbol": symbol,
                "period": period,
                "count": count,
                "adjust": adjust,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        return data or {}

    def quotes(self, symbols: Sequence[str]) -> List[Dict[str, Any]]:
        """实时行情（free 档单次 ≤5 只、10 rpm）。"""
        data = self._get("/v1/quotes", {"symbols": ",".join(symbols)})
        if isinstance(data, list):
            return data
        return (data or {}).get("quotes") or (data or {}).get("data") or []

    def ex_factors(
        self,
        symbols: Sequence[str],
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """除权因子（starter+ 档；free 档返回 403 NO_EX_FACTORS_PERMISSION）。"""
        data = self._get(
            "/v1/klines/ex-factors",
            {"symbols": ",".join(symbols), "start_time": start_time, "end_time": end_time},
        )
        return data or {}

    def instruments(
        self,
        exchange: str = "SH",
        instrument_type: str = "stock",
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """交易所标的维表（free 档可用）。

        exchange ∈ SH/SZ/BJ（美股港交所代码见服务端文档）；单次 limit 覆盖
        全量即可，实测 SH 3660 只一次返回。item 含 symbol/name/ext，
        ext 里有 listing_date/total_shares/float_shares/limit_up/limit_down。
        """
        data = self._get(
            f"/v1/exchanges/{exchange}/instruments",
            {"instrument_type": instrument_type, "limit": limit},
        )
        if isinstance(data, list):
            return data
        return (data or {}).get("data") or []

    def detect_tier(self) -> str:
        """探测 key 档位：none（无效/未配置）/ free / starter+。

        判据与 tick-stock-panel 的探测分水岭一致：
        有单标的日K = key 有效；有除权因子 = 付费档，否则免费档。
        """
        if not self.api_key:
            return "none"
        try:
            self.klines("600000.SH", period="1d", count=1, adjust="none")
        except TickflowError:
            return "none"
        try:
            self.ex_factors(["600000.SH"], start_time=0)
        except TickflowError:
            return "free"
        return "paid"
