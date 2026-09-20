"""research_report_service 契约测试（fake 客户端注入，不发真实请求）。"""

import time
from urllib.parse import quote

import fitz
import pytest

from app.services import research_report_service as rrs
from app.utils.data_sources.eastmoney_report_client import EastmoneyReportError

pytestmark = pytest.mark.module_data_jobs


def _make_pdf(text: str = "") -> bytes:
    """用 PyMuPDF 现场造一个最小 PDF（有/无文字层两种）。

    按行写入且每行控制在页宽内——超出 mediabox 的字符不会被提取。
    """
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    for line in text.splitlines() or []:
        page.insert_text((72, y), line, fontname="china-s")
        y += 20.0
    return doc.tobytes()


def _info_row(**overrides):
    row = {
        "title": "2026年中报点评：茅台酒稳健",
        "stockName": "贵州茅台",
        "stockCode": "600519",
        "orgCode": "10000296",
        "orgName": "西南证券股份有限公司",
        "orgSName": "西南证券",
        "publishDate": "2026-08-21 00:00:00.000",
        "infoCode": "AP202608211828244348",
        "industryName": "",
        "indvInduName": "白酒Ⅱ",
        "emRatingName": "买入",
        "sRatingName": "买入",
        "researcher": "朱会振,舒尚立",
        "attachPages": "4",
        "encodeUrl": "abc=",
    }
    row.update(overrides)
    return row


def _jg_row(**overrides):
    row = {
        "id": 273000001563278742,
        "title": "北交所定期报告",
        "orgSName": "东吴证券",
        "publishDate": "2026-09-20 00:00:00.000",
        "encodeUrl": "2jQewT+GbMEM=",
        "researcher": "朱洁羽",
        "industryName": "",
    }
    row.update(overrides)
    return row


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.rows_by_category = {"industry": [_info_row()], "strategy": [_jg_row()]}
        self.totals = {"industry": 1, "strategy": 1}
        self.error = None
        self.pdf_bytes = _make_pdf(
            "贵州茅台 2026 年中报点评：茅台酒稳健，系列酒主动调整。\n"
            "买入（维持），当前价 1297.99 元，目标价 1550 元。\n"
            "盈利预测：2026 年 EPS 69.83 元，PE 18.59 倍。"
        )
        self.downloads = []
        self.jg_resolved = ("AP202609201829659331", "https://pdf.dfcfw.com/pdf/H3_AP202609201829659331_1.pdf")

    def search_reports(self, category, page=1, size=20, begin_date="", end_date="", code=""):
        self.calls.append((category, page, size, begin_date, end_date, code))
        if self.error is not None:
            raise self.error
        rows = self.rows_by_category.get(category, [])
        return rows, self.totals.get(category, len(rows)), 1

    def download_pdf(self, pdf_url, dest_path):
        """模拟真实 client 契约：魔数不对抛 EastmoneyReportError，落盘成功才写文件。"""
        self.downloads.append(pdf_url)
        from pathlib import Path

        if self.pdf_bytes[:5] != b"%PDF-":
            raise EastmoneyReportError("bad_pdf", "下载内容不是 PDF")
        Path(dest_path).write_bytes(self.pdf_bytes)

    def fetch_jg_pdf_url(self, category, encode):
        self.calls.append(("jgpdf", category, encode))
        return self.jg_resolved


@pytest.fixture()
def service(tmp_path):
    return rrs.ResearchReportService(client=_FakeClient(), pdf_cache_dir=tmp_path)


def test_normalizes_info_code_row(service):
    payload = service.search_reports("industry", begin="20260601", end="20260920")
    assert payload["total"] == 1
    assert payload["begin"] == "2026-06-01"
    assert payload["end"] == "2026-09-20"
    row = payload["items"][0]
    assert row["stock_code"] == "600519"
    assert row["org_name"] == "西南证券"
    assert row["publish_date"] == "2026-08-21"
    # industryName 为空时回退 indvInduName
    assert row["industry_name"] == "白酒Ⅱ"
    assert row["pages"] == 4
    assert row["detail_url"] == (
        "https://data.eastmoney.com/report/info/AP202608211828244348.html"
    )
    assert row["pdf_url"] == "https://pdf.dfcfw.com/pdf/H3_AP202608211828244348_1.pdf"


def test_normalizes_jg_row_with_quoted_encode_url(service):
    payload = service.search_reports("strategy", begin="20260901", end="20260920")
    row = payload["items"][0]
    expected = (
        "https://data.eastmoney.com/report/zw_strategy.jshtml?encodeUrl="
        + quote("2jQewT+GbMEM=", safe="")
    )
    assert row["detail_url"] == expected
    # jg 无 infoCode，无 PDF、无页数
    assert row["pdf_url"] is None
    assert row["info_code"] is None
    assert row["pages"] is None


def test_stock_category_requires_six_digit_code(service):
    with pytest.raises(ValueError):
        service.search_reports("stock", code="")
    with pytest.raises(ValueError):
        service.search_reports("stock", code="60051")
    # 带后缀自动截取 6 位数字
    payload = service.search_reports("stock", code="600519.SH")
    assert service.client.calls[-1][5] == "600519"


def test_rejects_bad_category_and_dates(service):
    with pytest.raises(ValueError):
        service.search_reports("week")
    with pytest.raises(ValueError):
        service.search_reports("industry", begin="2026-06-01")
    with pytest.raises(ValueError):
        service.search_reports("industry", begin="20260920", end="20260601")


def test_cache_hit_avoids_second_fetch(service):
    service.search_reports("industry", begin="20260601", end="20260920")
    payload = service.search_reports("industry", begin="20260601", end="20260920")
    assert len(service.client.calls) == 1
    assert payload["cached"] is True
    # 不同 code/page 是独立缓存键
    service.search_reports("industry", begin="20260601", end="20260920", page=2)
    assert len(service.client.calls) == 2


def test_serves_stale_on_upstream_error(service, monkeypatch):
    service.search_reports("industry", begin="20260601", end="20260920")

    service.client.error = EastmoneyReportError("network", "down")
    # 跳到新鲜期外、1 小时回供窗口内
    real_monotonic = time.monotonic()
    monkeypatch.setattr(
        rrs.time, "monotonic", lambda: real_monotonic + rrs.CACHE_FRESH_SECONDS + 1800
    )
    payload = service.search_reports("industry", begin="20260601", end="20260920")
    assert payload["stale"] is True
    assert payload["items"][0]["info_code"] == "AP202608211828244348"

    # 超出回供窗口则抛错
    monkeypatch.setattr(
        rrs.time,
        "monotonic",
        lambda: real_monotonic + rrs.CACHE_FRESH_SECONDS + rrs.STALE_SERVE_SECONDS + 60,
    )
    with pytest.raises(EastmoneyReportError):
        service.search_reports("industry", begin="20260601", end="20260920")


# ---- 研报正文（PDF 下载 + 文本提取） ----


def test_content_downloads_and_extracts(service, tmp_path):
    payload = service.get_report_content(info_code="AP202608211828244348")
    assert payload["info_code"] == "AP202608211828244348"
    assert payload["total_pages"] == 1
    assert "贵州茅台" in payload["pages"][0]["text"]
    assert payload["image_only"] is False
    # PDF 落盘到缓存目录
    assert (tmp_path / "AP202608211828244348.pdf").exists()


def test_content_reuses_disk_cache(service):
    service.get_report_content(info_code="AP202608211828244348")
    payload = service.get_report_content(info_code="AP202608211828244348")
    assert len(service.client.downloads) == 1
    assert payload["total_chars"] > 0


def test_content_rejects_bad_info_code(service):
    with pytest.raises(ValueError):
        service.get_report_content(info_code="600519")
    with pytest.raises(ValueError):
        service.get_report_content()


def test_content_bad_magic_raises_and_leaves_no_cache(service):
    service.client.pdf_bytes = b"<html>anti-bot challenge</html>"
    with pytest.raises(EastmoneyReportError):
        service.get_report_content(info_code="AP202608211828244348")


def test_content_jg_resolves_via_detail_page(service):
    payload = service.get_report_content(category="strategy", encode="2jQewT+GbMEM=")
    assert ("jgpdf", "strategy", "2jQewT+GbMEM=") in service.client.calls
    assert service.client.downloads == [
        "https://pdf.dfcfw.com/pdf/H3_AP202609201829659331_1.pdf"
    ]
    assert payload["info_code"] == "AP202609201829659331"
    # 解析结果有内存缓存，二次调用不再抓详情页
    service.get_report_content(category="strategy", encode="2jQewT+GbMEM=")
    assert service.client.calls.count(("jgpdf", "strategy", "2jQewT+GbMEM=")) == 1


def test_content_jg_requires_valid_category(service):
    with pytest.raises(ValueError):
        service.get_report_content(encode="abc", category="industry")


def test_content_detects_image_only_pdf(service):
    service.client.pdf_bytes = _make_pdf("")  # 无文字层
    payload = service.get_report_content(info_code="AP202608211828244348")
    assert payload["image_only"] is True
    assert payload["total_chars"] == 0
