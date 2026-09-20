"""东方财富研报中心 REST 客户端（reportapi.eastmoney.com，公开接口无需鉴权）。

实测契约（2026-09-20）：
- 行业 ``GET /report/list``（qType=1）；个股 ``POST /report/list2`` 必须用
  JSON body（GET 405 / form 415，qType=0 + 6 位 code）；策略与宏观共用
  ``GET /report/jg``（qType=2 / qType=3）；新股 ``GET /report/newStockList``
- ``beginTime`` 为必填（缺失返回 400），日期格式 ``YYYY-MM-DD``
- 响应为裸 JSON：``{hits, size, data, TotalPage, pageNo, ...}``，
  content-type 是 text/plain，无结果时 data 为空列表
- ``jg`` 条目无 infoCode，以 ``encodeUrl`` 标识，也没有 attachPages；
  其余三类有 infoCode（详情页 /report/info/{infoCode}.html，PDF 见服务层拼装）
- 同源 PDF 站点 pdf.dfcfw.com 对 python-requests 有 TLS 指纹反爬（返回 JS 挑战
  脚本），浏览器访问正常——客户端不负责 PDF 下载
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

BASE_URL = "https://reportapi.eastmoney.com"
DEFAULT_TIMEOUT_SECONDS = 15
#: 公网匿名接口，节流放宽到 0.5s/次
DEFAULT_THROTTLE_SECONDS = 0.5
#: PDF 下载走 curl 子进程，超时单独放宽
PDF_CURL_TIMEOUT_SECONDS = 60

#: 详情页 / PDF 的 URL 模板（infoCode 类研报）
DETAIL_URL_TEMPLATE = "https://data.eastmoney.com/report/info/{info_code}.html"
PDF_URL_TEMPLATE = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
#: jg 类（策略/宏观）详情页按 encodeUrl 跳转
JG_DETAIL_TEMPLATES = {
    "strategy": "https://data.eastmoney.com/report/zw_strategy.jshtml?encodeUrl={encoded}",
    "macro": "https://data.eastmoney.com/report/zw_macresearch.jshtml?encodeUrl={encoded}",
}

#: 类别 → (端点, 方法, qType)
CATEGORY_ENDPOINTS = {
    "industry": ("/report/list", "GET", "1"),
    "stock": ("/report/list2", "POST_JSON", "0"),
    "strategy": ("/report/jg", "GET", "2"),
    "macro": ("/report/jg", "GET", "3"),
    "new_stock": ("/report/newStockList", "GET", None),
}

#: 详情页 HTML 里的 PDF 直链（策略/宏观列表接口无 infoCode，需从详情页解析）
_DETAIL_PDF_RE = re.compile(r"(https://pdf\.dfcfw\.com/pdf/H3_([A-Z0-9]+)_1\.pdf)")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
}


class EastmoneyReportError(RuntimeError):
    """东财研报接口错误（HTTP 非 200 或响应不是 JSON）。"""

    def __init__(self, code: Any, message: str):
        super().__init__(f"eastmoney report error code={code}: {message}")
        self.code = code
        self.message = message


class EastmoneyReportClient:
    """东财研报客户端：请求节流 + 四端点统一取数。

    客户端只负责取数与解析外层分页字段，条目字段归一化由服务层完成。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        throttle_seconds: Optional[float] = None,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.timeout = timeout
        self.throttle_seconds = (
            throttle_seconds if throttle_seconds is not None else DEFAULT_THROTTLE_SECONDS
        )
        self._session = session or requests.Session()
        self._throttle_lock = threading.Lock()
        self._last_request_monotonic = 0.0

    def _throttle(self) -> None:
        if self.throttle_seconds <= 0:
            return
        with self._throttle_lock:
            wait = self._last_request_monotonic + self.throttle_seconds - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request_monotonic = time.monotonic()

    def _request(self, method: str, path: str, params: Dict[str, Any]) -> Any:
        self._throttle()
        url = f"{self.base_url}{path}"
        try:
            if method == "POST_JSON":
                resp = self._session.post(
                    url, json=params, headers=_HEADERS, timeout=self.timeout
                )
            else:
                resp = self._session.get(
                    url, params=params, headers=_HEADERS, timeout=self.timeout
                )
        except requests.RequestException as exc:
            raise EastmoneyReportError("network", f"东财研报请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise EastmoneyReportError(
                resp.status_code, f"东财研报 HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise EastmoneyReportError(
                "bad_json", f"东财研报响应不是 JSON: {resp.text[:200]}"
            ) from exc

    def search_reports(
        self,
        category: str,
        page: int = 1,
        size: int = 20,
        begin_date: str = "",
        end_date: str = "",
        code: str = "",
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """按类别检索研报，返回 (条目列表, 总数, 总页数)。

        begin_date/end_date 为 ``YYYY-MM-DD``；code 仅 stock 类别使用（6 位数字）。
        category 白名单见 CATEGORY_ENDPOINTS，未知类别抛 ValueError。
        """
        if category not in CATEGORY_ENDPOINTS:
            raise ValueError(f"未知研报类别: {category}")
        path, method, q_type = CATEGORY_ENDPOINTS[category]

        params: Dict[str, Any] = {
            "pageSize": int(size),
            "pageNo": int(page),
            "beginTime": begin_date,
            "endTime": end_date,
        }
        if category in ("industry", "stock"):
            params.update(
                {
                    "qType": q_type,
                    "industry": "*",
                    "industryCode": "*",
                    "rating": "*",
                    "ratingChange": "*",
                    "orgCode": "",
                    "rcode": "",
                    "fields": "",
                }
            )
        if category == "stock":
            params["code"] = code
        elif category in ("strategy", "macro"):
            params.update({"qType": q_type, "orgCode": ""})

        payload = self._request(method, path, params) or {}
        rows = payload.get("data") or []
        total = int(payload.get("hits") or 0)
        try:
            pages = int(payload.get("TotalPage") or 0)
        except (TypeError, ValueError):
            pages = 0
        return rows, total, pages

    # ---- 研报正文（PDF 附件） ----

    def fetch_jg_pdf_url(self, category: str, encode_url: str) -> Tuple[str, str]:
        """抓策略/宏观详情页 HTML，解析出 (info_code, pdf_url)。

        详情页在 data.eastmoney.com 上，requests 可直接访问（TLS 指纹反爬
        仅部署在 pdf.dfcfw.com 的附件下载上）。
        """
        template = JG_DETAIL_TEMPLATES.get(category)
        if not template:
            raise ValueError(f"类别 {category} 不支持详情页解析（须为 strategy/macro）")
        url = template.format(encoded=quote(encode_url, safe=""))
        self._throttle()
        try:
            resp = self._session.get(url, headers=_HEADERS, timeout=self.timeout)
        except requests.RequestException as exc:
            raise EastmoneyReportError("network", f"研报详情页请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise EastmoneyReportError(
                resp.status_code, f"研报详情页 HTTP {resp.status_code}"
            )
        found = _DETAIL_PDF_RE.search(resp.text)
        if not found:
            raise EastmoneyReportError("no_pdf", "研报详情页未找到 PDF 附件链接")
        return found.group(2), found.group(1)

    def download_pdf(self, pdf_url: str, dest_path: Path) -> Path:
        """用 curl 子进程下载 PDF 附件（requests 的 TLS 指纹会触发反爬挑战）。

        .part 临时文件 + 原子改名（同 fuyao download_dump 模式）；
        下载后校验 %PDF 魔数，反爬挑战页/无效编号会在这一步暴露。
        """
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest_path.with_suffix(dest_path.suffix + f".part.{os.getpid()}")
        self._throttle()
        try:
            try:
                proc = subprocess.run(
                    [
                        "curl",
                        "-sS",
                        "--max-time",
                        str(PDF_CURL_TIMEOUT_SECONDS),
                        "-o",
                        str(part_path),
                        pdf_url,
                    ],
                    capture_output=True,
                    timeout=PDF_CURL_TIMEOUT_SECONDS + 10,
                )
            except OSError as exc:
                raise EastmoneyReportError("curl_missing", f"curl 不可用: {exc}") from exc
            if proc.returncode != 0:
                stderr = proc.stderr.decode(errors="ignore")[:200]
                raise EastmoneyReportError("curl", f"PDF 下载失败 rc={proc.returncode}: {stderr}")
            with open(part_path, "rb") as fh:
                magic = fh.read(5)
            if magic != b"%PDF-":
                size = part_path.stat().st_size
                raise EastmoneyReportError(
                    "bad_pdf", f"下载内容不是 PDF（{size}B，可能触发反爬或编号无效）"
                )
            part_path.replace(dest_path)
        finally:
            if part_path.exists():
                part_path.unlink(missing_ok=True)
        return dest_path
