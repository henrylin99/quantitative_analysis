"""research_api 契约测试（fake 服务注入）。"""

import pytest
from flask import Flask

from app.api.research_api import research_bp

pytestmark = pytest.mark.module_data_jobs


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(research_bp)
    return app


class _FakeService:
    def __init__(self):
        self.kwargs = {}
        self.payload = {
            "category": "industry",
            "category_label": "行业研报",
            "begin": "2026-06-22",
            "end": "2026-09-20",
            "page": 1,
            "size": 20,
            "total": 1,
            "pages": 1,
            "items": [
                {
                    "category": "industry",
                    "info_code": "AP202609201829659418",
                    "title": "8月社零报告专题",
                    "stock_code": None,
                    "stock_name": None,
                    "org_name": "东海证券",
                    "publish_date": "2026-09-20",
                    "industry_name": "一般零售",
                    "rating": "增持",
                    "researchers": "吴康辉",
                    "pages": 14,
                    "detail_url": "https://data.eastmoney.com/report/info/AP202609201829659418.html",
                    "pdf_url": "https://pdf.dfcfw.com/pdf/H3_AP202609201829659418_1.pdf",
                }
            ],
        }

    def search_reports(self, category, page=1, size=20, begin=None, end=None, code=None):
        self.kwargs = {
            "category": category,
            "page": page,
            "size": size,
            "begin": begin,
            "end": end,
            "code": code,
        }
        return self.payload

    def get_report_content(self, info_code=None, category=None, encode=None):
        self.kwargs = {
            "info_code": info_code,
            "category": category,
            "encode": encode,
        }
        return {
            "info_code": info_code or "AP202609201829659331",
            "pdf_url": "https://pdf.dfcfw.com/pdf/H3_AP202609201829659331_1.pdf",
            "total_pages": 2,
            "total_chars": 100,
            "image_only": False,
            "truncated": False,
            "pages": [{"page": 1, "text": "正文"}],
        }


@pytest.fixture()
def fake_service(monkeypatch):
    service = _FakeService()
    monkeypatch.setattr(
        "app.api.research_api.get_research_report_service", lambda: service
    )
    return service


def test_reports_validates_category(app, fake_service):
    assert app.test_client().get("/api/research/reports?category=week").status_code == 400
    assert app.test_client().get("/api/research/reports").status_code == 400


def test_reports_validates_dates(app, fake_service):
    assert (
        app.test_client().get("/api/research/reports?category=industry&begin=2026-09-01").status_code
        == 400
    )
    assert (
        app.test_client().get("/api/research/reports?category=industry&end=abc").status_code == 400
    )


def test_reports_validates_page_size(app, fake_service):
    assert app.test_client().get("/api/research/reports?category=industry&page=x").status_code == 400
    assert app.test_client().get("/api/research/reports?category=industry&size=999").status_code == 200


def test_reports_returns_envelope_and_passes_params(app, fake_service):
    resp = app.test_client().get(
        "/api/research/reports?category=stock&begin=20260101&end=20260920&page=2&size=50&code=600519"
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["code"] == 200
    assert payload["data"]["items"][0]["info_code"] == "AP202609201829659418"
    assert fake_service.kwargs == {
        "category": "stock",
        "page": 2,
        "size": 50,
        "begin": "20260101",
        "end": "20260920",
        "code": "600519",
    }


def test_reports_error_envelope_on_service_exception(app, monkeypatch):
    class _Boom:
        def search_reports(self, **_):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.api.research_api.get_research_report_service", lambda: _Boom())
    resp = app.test_client().get("/api/research/reports?category=industry")
    assert resp.status_code == 500
    assert resp.get_json()["code"] == 500


# ---- /api/research/content ----


def test_content_requires_params(app, fake_service):
    assert app.test_client().get("/api/research/content").status_code == 400
    # encode 必须搭配 strategy/macro
    assert (
        app.test_client().get("/api/research/content?encode=abc&category=industry").status_code
        == 400
    )
    assert app.test_client().get("/api/research/content?encode=abc").status_code == 400


def test_content_validates_info_code(app, fake_service):
    assert (
        app.test_client().get("/api/research/content?info_code=600519").status_code == 400
    )


def test_content_envelope_with_info_code(app, fake_service):
    resp = app.test_client().get("/api/research/content?info_code=AP202608211828244348")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["code"] == 200
    assert payload["data"]["pages"][0]["text"] == "正文"
    assert fake_service.kwargs == {
        "info_code": "AP202608211828244348",
        "category": None,
        "encode": None,
    }


def test_content_envelope_with_jg_encode(app, fake_service):
    resp = app.test_client().get(
        "/api/research/content?category=strategy&encode=2jQewT%2B"
    )
    assert resp.status_code == 200
    assert fake_service.kwargs == {
        "info_code": None,
        "category": "strategy",
        "encode": "2jQewT+",
    }


def test_content_info_code_takes_precedence(app, fake_service):
    """列表条目同时带 info_code 与 encodeUrl 时，以 info_code 为准不误拒。"""
    resp = app.test_client().get(
        "/api/research/content?info_code=AP202608211828244348"
        "&category=industry&encode=2jQewT%2B"
    )
    assert resp.status_code == 200
    assert fake_service.kwargs["info_code"] == "AP202608211828244348"


def test_content_upstream_error_is_502(app, monkeypatch):
    from app.utils.data_sources.eastmoney_report_client import EastmoneyReportError

    class _Boom:
        def get_report_content(self, **_):
            raise EastmoneyReportError("bad_pdf", "下载内容不是 PDF")

    monkeypatch.setattr("app.api.research_api.get_research_report_service", lambda: _Boom())
    resp = app.test_client().get("/api/research/content?info_code=AP202608211828244348")
    assert resp.status_code == 502
    assert resp.get_json()["code"] == 502
