"""研报中心服务：东方财富研报检索（行业/个股/策略/宏观/新股）与正文提取。

- 归一化：四端点字段映射为统一 snake_case schema，并拼装详情页/PDF 链接
  （infoCode 类 → /report/info/{infoCode}.html + pdf.dfcfw.com H3 PDF；
  jg 类（策略/宏观）无 infoCode，按 encodeUrl 跳 zw_strategy/zw_macresearch）
- 缓存：进程内 TTL 10 分钟，容量上限 64；东财异常时 1 小时内回供 stale
- 正文：PDF 附件 curl 下载（requests 有 TLS 指纹反爬）+ 磁盘永久缓存
  data/research_pdfs/，PyMuPDF 提取全文；策略/宏观先从详情页解析附件链接
- 参数：对外日期口径 YYYYMMDD（与 market API 一致），对东财转 YYYY-MM-DD
"""

from __future__ import annotations

import copy
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from loguru import logger

from app.services.market_snapshot_service import evict_oldest
from app.utils.data_sources.eastmoney_report_client import (
    DETAIL_URL_TEMPLATE,
    JG_DETAIL_TEMPLATES,
    PDF_URL_TEMPLATE,
    EastmoneyReportClient,
    EastmoneyReportError,
)

CACHE_FRESH_SECONDS = 600.0
STALE_SERVE_SECONDS = 3600.0
CACHE_MAX_ENTRIES = 64

VALID_CATEGORIES = ("industry", "stock", "strategy", "macro", "new_stock")
CATEGORY_LABELS = {
    "industry": "行业研报",
    "stock": "个股研报",
    "strategy": "策略报告",
    "macro": "宏观研究",
    "new_stock": "新股研报",
}

_DATE_COMPACT_RE = re.compile(r"\d{8}")
_CODE_DIGITS_RE = re.compile(r"\D")
_INFO_CODE_RE = re.compile(r"AP\d{8,20}")

DEFAULT_WINDOW_DAYS = 90

#: 研报 PDF 磁盘缓存（研报发布后内容不变，永久缓存；data/ 已被 gitignore）
PDF_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "research_pdfs"
#: 平均每页可提取字符低于该值视为图片型（扫描/截图研报，无文字层）
IMAGE_ONLY_CHARS_PER_PAGE = 60
#: 单篇返回正文上限（超长研报截断，PDF 仍在磁盘可完整阅读）
MAX_TOTAL_CHARS = 150_000
#: encode → pdf 链接解析结果内存缓存上限
JG_PDF_URL_CACHE_MAX = 256


def _beijing_today() -> datetime:
    """北京时间当日（东财数据的自然日口径）。"""
    from app.utils.data_sources.fuyao_client import BEIJING_TZ

    return datetime.now(BEIJING_TZ)


class ResearchReportService:
    """进程内单例（get_research_report_service），线程安全。"""

    def __init__(
        self,
        client: Optional[EastmoneyReportClient] = None,
        pdf_cache_dir: Optional[Path] = None,
    ):
        self._client = client
        self._lock = threading.Lock()
        self._cache: Dict[Tuple[str, str, str, int, int, str], Tuple[float, Dict[str, Any]]] = {}
        self.pdf_cache_dir = Path(pdf_cache_dir) if pdf_cache_dir else PDF_CACHE_DIR
        self._download_lock = threading.Lock()
        self._jg_pdf_url_cache: Dict[Tuple[str, str], Tuple[str, str]] = {}

    @property
    def client(self) -> EastmoneyReportClient:
        if self._client is None:
            self._client = EastmoneyReportClient()
        return self._client

    def search_reports(
        self,
        category: str,
        page: int = 1,
        size: int = 20,
        begin: Optional[str] = None,
        end: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """研报检索（category 白名单见 VALID_CATEGORIES）。

        begin/end 为 YYYYMMDD 可空（默认近 90 天 ~ 今天，北京时区）；
        code 仅 stock 类别生效，接受 600519 / 600519.SH 等写法，截取 6 位数字。
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(f"category 取值须为 {'/'.join(VALID_CATEGORIES)}")
        page = max(1, int(page))
        size = min(50, max(1, int(size)))
        begin_iso = self._resolve_date(begin, default_days_ago=DEFAULT_WINDOW_DAYS)
        end_iso = self._resolve_date(end, default_days_ago=0)
        cleaned_code = self._clean_code(category, code)
        if begin_iso > end_iso:
            raise ValueError("begin 不能晚于 end")

        key = (category, begin_iso, end_iso, page, size, cleaned_code or "")
        with self._lock:
            cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_FRESH_SECONDS:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            return payload

        try:
            rows, total, pages = self.client.search_reports(
                category,
                page=key[3],
                size=key[4],
                begin_date=key[1],
                end_date=key[2],
                code=key[5],
            )
        except EastmoneyReportError as exc:
            if cached and time.monotonic() - cached[0] < CACHE_FRESH_SECONDS + STALE_SERVE_SECONDS:
                logger.warning(f"[research] 东财拉取失败，回供过期缓存: {exc}")
                payload = copy.deepcopy(cached[1])
                payload.update({"cached": True, "stale": True})
                return payload
            raise

        payload = {
            "category": category,
            "category_label": CATEGORY_LABELS.get(category, category),
            "begin": key[1],
            "end": key[2],
            "page": key[3],
            "size": key[4],
            "total": total,
            "pages": pages,
            "items": [self._normalize(category, row) for row in rows],
        }
        with self._lock:
            evict_oldest(self._cache, CACHE_MAX_ENTRIES)
            self._cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    # ---- 研报正文（PDF 下载 + 文本提取） ----

    def get_report_content(
        self,
        info_code: Optional[str] = None,
        category: Optional[str] = None,
        encode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """研报正文：PDF 磁盘缓存（永久）→ PyMuPDF 文本提取。

        info_code 类（行业/个股/新股）直接拼 PDF 直链；策略/宏观列表接口无
        infoCode，须传 category+encode 先从详情页解析出附件链接。
        图片型（扫描）研报提取字符接近 0，image_only 标记后由前端引导看 PDF。
        """
        if info_code:
            code = str(info_code).strip().upper()
            if not _INFO_CODE_RE.fullmatch(code):
                raise ValueError(f"info_code 格式不合法（AP 开头编号），收到: {info_code}")
            resolved_code, pdf_url = code, PDF_URL_TEMPLATE.format(info_code=code)
        elif encode:
            if category not in JG_DETAIL_TEMPLATES:
                raise ValueError("encode 参数须配合 category=strategy/macro 使用")
            resolved_code, pdf_url = self._resolve_jg_pdf_url(category, str(encode).strip())
        else:
            raise ValueError("需要 info_code，或 category(strategy/macro)+encode 参数")

        pdf_path = self._ensure_pdf(resolved_code, pdf_url)
        return self._extract_pdf_text(resolved_code, pdf_url, pdf_path)

    def _resolve_jg_pdf_url(self, category: str, encode: str) -> Tuple[str, str]:
        """encode → (info_code, pdf_url)，解析结果内存缓存（详情页链接不变）。"""
        key = (category, encode)
        with self._lock:
            cached = self._jg_pdf_url_cache.get(key)
        if cached:
            return cached
        resolved = self.client.fetch_jg_pdf_url(category, encode)
        with self._lock:
            if len(self._jg_pdf_url_cache) >= JG_PDF_URL_CACHE_MAX:
                self._jg_pdf_url_cache.clear()
            self._jg_pdf_url_cache[key] = resolved
        return resolved

    def _ensure_pdf(self, info_code: str, pdf_url: str) -> Path:
        """PDF 磁盘缓存命中直接返回；未命中串行下载（防并发重复抓）。"""
        dest = self.pdf_cache_dir / f"{info_code}.pdf"
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        with self._download_lock:
            if dest.exists() and dest.stat().st_size > 0:
                return dest
            self.client.download_pdf(pdf_url, dest)
        return dest

    @staticmethod
    def _extract_pdf_text(info_code: str, pdf_url: str, pdf_path: Path) -> Dict[str, Any]:
        import fitz  # 延迟导入：PyMuPDF 加载较重，仅在首次提取时付出成本

        pages: List[Dict[str, Any]] = []
        total_chars = 0
        truncated = False
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:  # noqa: BLE001  磁盘缓存损坏等，按上游内容错误处理
            raise EastmoneyReportError("parse", f"PDF 解析失败: {exc}") from exc
        with doc:
            total_pages = len(doc)
            for index, page in enumerate(doc, start=1):
                text = page.get_text("text")
                # 过滤单字符行：竖排栏目装饰字与页码碎片
                lines = [line.strip() for line in text.splitlines()]
                cleaned = "\n".join(line for line in lines if len(line) > 1).strip()
                total_chars += len(cleaned)
                pages.append({"page": index, "text": cleaned})
                if total_chars >= MAX_TOTAL_CHARS:
                    truncated = True
                    break
        image_only = total_pages > 0 and total_chars < IMAGE_ONLY_CHARS_PER_PAGE * total_pages
        return {
            "info_code": info_code,
            "pdf_url": pdf_url,
            "total_pages": total_pages,
            "total_chars": total_chars,
            "image_only": image_only,
            "truncated": truncated,
            "pages": pages,
        }

    # ---- 参数辅助 ----

    @staticmethod
    def _resolve_date(value: Optional[str], default_days_ago: int) -> str:
        """YYYYMMDD → YYYY-MM-DD；空值按 default_days_ago 回退（0=今天）。"""
        if value is None or str(value).strip() == "":
            day = _beijing_today() - timedelta(days=default_days_ago)
            return day.strftime("%Y-%m-%d")
        text = str(value).strip()
        if not _DATE_COMPACT_RE.fullmatch(text):
            raise ValueError(f"date 格式应为 YYYYMMDD，收到: {value}")
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"

    @staticmethod
    def _clean_code(category: str, code: Optional[str]) -> Optional[str]:
        if category != "stock":
            return None
        digits = _CODE_DIGITS_RE.sub("", str(code or ""))
        if len(digits) != 6:
            raise ValueError("stock 类别须提供 6 位数字的股票代码（如 600519）")
        return digits

    # ---- 归一化 ----

    @classmethod
    def _normalize(cls, category: str, row: Dict[str, Any]) -> Dict[str, Any]:
        info_code = cls._text(row.get("infoCode"))
        encode_url = cls._text(row.get("encodeUrl"))
        if info_code:
            detail_url = DETAIL_URL_TEMPLATE.format(info_code=info_code)
            pdf_url = PDF_URL_TEMPLATE.format(info_code=info_code)
        elif category in JG_DETAIL_TEMPLATES and encode_url:
            detail_url = JG_DETAIL_TEMPLATES[category].format(encoded=quote(encode_url, safe=""))
            pdf_url = None
        else:
            detail_url = "https://data.eastmoney.com/report/"
            pdf_url = None
        return {
            "category": category,
            "info_code": info_code,
            "encode_url": encode_url,
            "title": cls._text(row.get("title")),
            "stock_code": cls._text(row.get("stockCode")),
            "stock_name": cls._text(row.get("stockName")),
            "org_name": cls._text(row.get("orgSName")) or cls._text(row.get("orgName")),
            "publish_date": cls._date_only(row.get("publishDate")),
            "industry_name": cls._text(row.get("industryName")) or cls._text(row.get("indvInduName")),
            "rating": cls._text(row.get("emRatingName")) or cls._text(row.get("sRatingName")),
            "researchers": cls._text(row.get("researcher")),
            "pages": cls._int_or_none(row.get("attachPages")),
            "detail_url": detail_url,
            "pdf_url": pdf_url,
        }

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _date_only(value: Any) -> Optional[str]:
        text = ResearchReportService._text(value)
        return text.split(" ")[0] if text else None

    @staticmethod
    def _int_or_none(value: Any) -> Optional[int]:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError, AttributeError):
            return None


_service: Optional[ResearchReportService] = None
_service_lock = threading.Lock()


def get_research_report_service() -> ResearchReportService:
    global _service
    with _service_lock:
        if _service is None:
            _service = ResearchReportService()
        return _service
