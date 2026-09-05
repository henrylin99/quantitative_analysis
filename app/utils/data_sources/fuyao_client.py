"""扶摇（同花顺官方金融数据 API）REST 客户端。

接口契约参考 tick-stock-panel 项目（MIT License, Copyright (c) 2026
tickflow-stock-panel contributors）的 backend/app/plugins/fuyao/client.py，
按本项目技术栈改写为 requests 同步实现。该项目不携带此注释之外的义务。

契约要点：
- 认证：请求头 ``X-api-key``；key 从环境变量 FUYAO_API_KEY 读取
- 响应信封：``{code, message, data}``，code != 0 视为业务错误
  （4001 限频 / 1002 无效代码或非交易日 / 1003 超批量 / 5003 未披露报告期）
- 时间口径：所有 *ms 字段为北京时间零点的 epoch ms，统一用
  beijing_ms_to_ymd 解析（按 UTC 解析会偏一天）
- 字段双命名：快照接口实测返回 high_price/low_price/prev_price，
  官方文档为 highest_price/lowest_price/prev_close_price，取值时两者都试
- 节流：单请求间隔默认 0.12s（实测 200+ 连发未触发 4001）
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv

BEIJING_TZ = timezone(timedelta(hours=8))

BASE_URL = "https://fuyao.aicubes.cn"
API_KEY_ENV = "FUYAO_API_KEY"
DEFAULT_THROTTLE_SECONDS = 0.12
DEFAULT_TIMEOUT_SECONDS = 30

#: 快照单页条数（6000 覆盖全市场）
SNAPSHOT_PAGE_SIZE = 6000
#: thscodes 批量接口单次上限（快照批量/估值快照）
BATCH_LIMIT = 100
#: dump 下载分片大小（字节）
DUMP_CHUNK_SIZE = 1 << 20

FINANCIAL_STATEMENT_ENDPOINTS = {
    "income": "income-statements",
    "balance_sheet": "balance-sheets",
    "cash_flow": "cash-flow-statements",
}

_DUMP_RELEASE_RE = re.compile(r"releases/(\d{8})/")


def beijing_ms_to_ymd(value_ms: Optional[float]) -> Optional[str]:
    """北京时间零点的 epoch ms → YYYYMMDD。

    扶摇所有日期字段都是北京时间零点，按 UTC 解析会得到前一天。
    """
    if value_ms is None or value_ms != value_ms:  # NaN 防御
        return None
    try:
        dt = datetime.fromtimestamp(float(value_ms) / 1000.0, tz=BEIJING_TZ)
    except (OverflowError, OSError, ValueError):
        return None
    return dt.strftime("%Y%m%d")


def now_ms() -> int:
    return int(time.time() * 1000)


def release_of(presigned_url: str) -> Optional[str]:
    """从预签名 URL 的 releases/<date>/ 路径提取 dump release 版本号。"""
    found = _DUMP_RELEASE_RE.search(presigned_url or "")
    return found.group(1) if found else None


class FuyaoError(RuntimeError):
    """扶摇业务错误（响应信封 code != 0 或 HTTP 非 2xx）。"""

    def __init__(self, code: Any, message: str):
        super().__init__(f"fuyao error code={code}: {message}")
        self.code = code
        self.message = message

    @property
    def is_rate_limited(self) -> bool:
        return str(self.code) == "4001"

    @property
    def is_invalid_code(self) -> bool:
        return str(self.code) == "1002"


class FuyaoClient:
    """扶摇 REST 客户端：请求节流 + 信封解包 + 各数据端点封装。

    客户端不做任何字段换算/归一化（那是 normalize 层的职责），
    只负责把端点返回的 data 原样交给调用方。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        throttle_seconds: Optional[float] = None,
        session: Optional[requests.Session] = None,
    ):
        # 与 db_utils 一致：脚本直接运行/被 API 调用时都先加载 .env
        load_dotenv()
        self.api_key = (api_key if api_key is not None else os.getenv(API_KEY_ENV, "")).strip()
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.timeout = timeout
        self.throttle_seconds = (
            throttle_seconds if throttle_seconds is not None else DEFAULT_THROTTLE_SECONDS
        )
        self._session = session or requests.Session()
        self._throttle_lock = threading.Lock()
        self._last_request_monotonic = 0.0

    # ---- 基础请求 ----

    def _throttle(self) -> None:
        if self.throttle_seconds <= 0:
            return
        with self._throttle_lock:
            wait = self._last_request_monotonic + self.throttle_seconds - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request_monotonic = time.monotonic()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.api_key:
            raise FuyaoError("no_key", f"未配置 {API_KEY_ENV}，请在 .env 中设置后重试")
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        self._throttle()
        try:
            resp = self._session.get(
                f"{self.base_url}{path}",
                headers={"X-api-key": self.api_key},
                params=clean_params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise FuyaoError("network", f"扶摇请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise FuyaoError(resp.status_code, f"扶摇 HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise FuyaoError("bad_json", f"扶摇响应不是 JSON: {resp.text[:200]}") from exc
        code = payload.get("code")
        if code != 0:
            raise FuyaoError(code, payload.get("message", ""))
        return payload.get("data")

    # ---- 行情快照 ----

    def snapshot_page(
        self,
        limit: int = SNAPSHOT_PAGE_SIZE,
        offset: int = 0,
        thscodes: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """A 股全市场实时快照，分页或按 thscodes 批量（≤100）。"""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if thscodes:
            params["thscodes"] = ",".join(thscodes[:BATCH_LIMIT])
            params.pop("limit")
            params.pop("offset")
        return self._get("/api/a-share/prices/snapshot", params) or {}

    def snapshot_all(self, max_pages: int = 50) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        """分页拉全市场快照，返回 (rows, 服务端时间戳ms)。"""
        rows: List[Dict[str, Any]] = []
        server_ts: Optional[int] = None
        for _ in range(max_pages):
            data = self.snapshot_page(limit=SNAPSHOT_PAGE_SIZE, offset=len(rows))
            items = data.get("item") or []
            rows.extend(items)
            ts = data.get("timestamp")
            if isinstance(ts, (int, float)) and server_ts is None:
                server_ts = int(ts)
            total = data.get("total") or data.get("count")
            if not items or (isinstance(total, (int, float)) and len(rows) >= int(total)):
                break
        return rows, server_ts

    def price_snapshot_batch(self, thscodes: Sequence[str]) -> List[Dict[str, Any]]:
        """按代码批量拉实时快照（单次 ≤100 只）。"""
        data = self.snapshot_page(thscodes=thscodes)
        return data.get("item") or []

    def index_snapshot(self, thscodes: Sequence[str]) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        """指数实时快照（沪深交易所指数 + 同花顺板块指数，无北交所）。

        未知代码会导致整批 1002 连坐，调用方需先过滤 .BJ 等不支持代码；
        批量上限 100 只，超量由调用方分批。
        """
        data = self._get(
            "/api/a-share-index/prices/snapshot",
            {"thscodes": ",".join(thscodes[:BATCH_LIMIT])},
        )
        items = data.get("item") or []
        ts = data.get("timestamp")
        return items, int(ts) if isinstance(ts, (int, float)) else None

    def ths_index_catalog(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """同花顺指数目录（tag: industry=行业 / cn_concept=概念，可空=全部）。

        实测 industry 320 条、cn_concept 390 条；item: {thscode, name}。
        """
        data = self._get("/api/a-share-index/catalog/ths-index-list", {"tag": tag})
        return data.get("item") or []

    def ths_index_constituents(self, thscode: str) -> List[Dict[str, Any]]:
        """同花顺指数成分股（item: {thscode, ticker, name}）。"""
        data = self._get(
            "/api/a-share-index/constituents/ths-stock-list",
            {"thscode": thscode},
        )
        return data.get("item") or []

    # ---- 历史日K ----

    def historical_kline(
        self,
        thscode: str,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
        interval: str = "1d",
        adjust: str = "none",
    ) -> List[Dict[str, Any]]:
        """单标的历史K线。adjust 锁定 none（服务端前复权有逐日漂移，禁用）。

        服务端单次窗口 ≤10 年，超长窗口由调用方分片。
        """
        data = self._get(
            "/api/a-share/prices/historical",
            {
                "thscode": thscode,
                "interval": interval,
                "adjust": adjust,
                "start": start_ms,
                "end": end_ms,
            },
        )
        return data.get("item") or []

    # ---- 财务 ----

    def financial_statement(
        self,
        table: str,
        thscode: str,
        limit: int = 20,
        period: str = "quarterly",
    ) -> List[Dict[str, Any]]:
        """单标的财务报表（income/balance_sheet/cash_flow），单次 ≤20 期。"""
        endpoint = FINANCIAL_STATEMENT_ENDPOINTS.get(table)
        if not endpoint:
            raise ValueError(f"未知财务表: {table}")
        data = self._get(
            f"/api/a-share/financials/{endpoint}",
            {"thscode": thscode, "period": period, "limit": limit},
        )
        return data.get("item") or []

    def valuations_snapshot(self, thscodes: Sequence[str]) -> List[Dict[str, Any]]:
        """估值快照（pe_ttm/pe_mrq/pb_mrq/ps_ttm/pcf_ttm），单次 ≤100 只。"""
        data = self._get(
            "/api/a-share/valuations/snapshot",
            {"thscodes": ",".join(thscodes[:BATCH_LIMIT])},
        )
        return data.get("item") or []

    # ---- 日历与特色数据 ----

    def trading_days(self) -> List[Dict[str, Any]]:
        """交易日历（固定近一年窗口，item: {date_ms, date}）。"""
        data = self._get("/api/a-share/calendar/trading-days")
        return data.get("item") or []

    def dragon_tiger_list(
        self, board_type: str = "all", date: Optional[str] = None
    ) -> Dict[str, Any]:
        """龙虎榜（board_type: all/org/hot_money；date 可空=最近发布日）。"""
        return self._get(
            "/api/a-share/special-data/dragon-tiger-list",
            {"board_type": board_type, "date": date},
        ) or {}

    def short_term_benchmark(self, date: Optional[str] = None) -> Dict[str, Any]:
        """盘前竞价短线风向标（date 可空；支持一年内历史）。"""
        return self._get(
            "/api/a-share/auction/short-term-benchmark",
            {"date": date},
        ) or {}

    def limit_up_pool(
        self,
        date_ms: Optional[int] = None,
        page: int = 1,
        size: int = 100,
        sort_field: str = "continue_day_cnt",
        sort_dir: str = "desc",
    ) -> Dict[str, Any]:
        """A 股涨停股票池（date_ms 为北京时间零点 epoch ms，可空=最近交易日）。

        实测字段：thscode/ticker/name/is_st/is_new/last_price/
        price_change_ratio_pct/limit_up_time/limit_up_reason/
        continue_day_text("5连板")/continue_day_cnt/seal_money/max_seal_money。
        非交易日不传 date_ms 会返回空列表（total=0），由调用方回退最近交易日。
        """
        return self._get(
            "/api/a-share/special-data/limit-up-pool",
            {
                "date_ms": date_ms,
                "page": page,
                "size": size,
                "sort_field": sort_field,
                "sort_dir": sort_dir,
            },
        ) or {}

    def limit_up_ladder(self) -> Dict[str, Any]:
        """连板天梯矩阵（近 30 个交易日）。

        data.item[].boards 键：two_board/three_board/four_board/five_board/
        six_board/seven_over（2 板至 7 板及以上），每档为个股列表
        （thscode/ticker/name/board_num/seal_nextday/sign_level）。
        """
        return self._get("/api/a-share/special-data/limit-up-ladder") or {}

    # ---- dump 下载 ----

    def dump_download_url(self, kind: str) -> Dict[str, Any]:
        """获取全市场 dump 的预签名下载地址（kind: adjustment-factors/daily-k-10d/daily-k）。"""
        return self._get(f"/api/dump/market-dumps/{kind}/download-url") or {}

    def download_dump(self, kind: str, dest_path: Path) -> Path:
        """下载 dump parquet 到本地（.part 临时文件 + 原子改名）。

        预签名 URL 的签名覆盖请求本身，不得携带 X-api-key 头，
        否则对象存储会校验失败。
        """
        info = self.dump_download_url(kind)
        url = info.get("presigned_url")
        if not url:
            raise FuyaoError("no_url", f"dump {kind} 未返回下载地址")
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest_path.with_suffix(dest_path.suffix + f".part.{os.getpid()}")
        try:
            with self._session.get(url, stream=True, timeout=self.timeout) as resp:
                if resp.status_code != 200:
                    raise FuyaoError(resp.status_code, f"dump {kind} 下载失败 HTTP {resp.status_code}")
                with open(part_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=DUMP_CHUNK_SIZE):
                        if chunk:
                            fh.write(chunk)
            part_path.replace(dest_path)
        finally:
            if part_path.exists():
                part_path.unlink(missing_ok=True)
        return dest_path
