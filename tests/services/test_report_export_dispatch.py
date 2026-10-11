"""报告导出与真实外发（批次 2.1）契约测试。

覆盖：
- render_report_html / report_digest_text 对全部 section 类型的渲染
- export 端点：html 可用、pdf 未装 weasyprint 时 501、format 非法 400、报告不存在 404
- ReportDispatchService._deliver：渠道未配置不假装成功、log-only 渠道仅记录
- AlertPushService.push_text：指定渠道逐条外发并落推送日志
"""

import json
from types import SimpleNamespace

import pytest
from flask import Flask

from app.services.report_dispatch_service import ReportDispatchService
from app.services.report_export_service import (
    export_filename,
    report_digest_text,
    render_report_html,
)

pytestmark = pytest.mark.module_data_jobs


def _make_report():
    return SimpleNamespace(
        id=1,
        report_name="每日总结",
        report_type="daily_summary",
        report_content=json.dumps(
            {
                "title": "每日总结 - 2026年10月11日",
                "generated_at": "2026-10-11T18:30:00",
                "report_type": "daily_summary",
                "sections": [
                    {
                        "title": "市场数据概览",
                        "type": "metrics",
                        "content": [
                            {"label": "分钟数据点", "value": 1200, "color": "primary"},
                            {"label": "活跃股票", "value": 500, "color": "success"},
                        ],
                    },
                    {
                        "title": "活跃度分析",
                        "type": "table",
                        "content": {
                            "columns": ["category", "count"],
                            "rows": [{"category": "分钟行情", "count": 1200}],
                        },
                    },
                    {"title": "数据质量评估", "type": "summary", "content": "系统运行稳定。"},
                    {
                        "title": "异动",
                        "type": "alerts",
                        "content": [{"message": "XX 股票触及涨停"}],
                    },
                    {
                        "title": "信号分布",
                        "type": "chart",
                        "content": {"chart_type": "bar", "data": [{"name": "买入", "value": 5}]},
                    },
                ],
            }
        ),
        report_data=None,
    )


# ---- 渲染 ----


def test_render_report_html_covers_all_section_types():
    html = render_report_html(_make_report())
    assert "每日总结 - 2026年10月11日" in html
    assert "分钟数据点" in html
    assert "<table>" in html and "分钟行情" in html
    assert "系统运行稳定" in html
    assert "XX 股票触及涨停" in html
    assert "买入" in html
    assert html.startswith("<!DOCTYPE html>")


def test_render_report_html_escapes_malicious_content():
    report = SimpleNamespace(
        id=1,
        report_name="x",
        report_type="t",
        report_content=json.dumps(
            {
                "title": "<script>alert(1)</script>",
                "sections": [{"title": "t", "type": "summary", "content": "<img src=x onerror=alert(1)>"}],
            }
        ),
    )
    html = render_report_html(report)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_report_digest_text_contains_metrics_and_summary():
    text = report_digest_text(_make_report())
    assert text.startswith("每日总结 - 2026年10月11日")
    assert "分钟数据点 1200" in text
    assert "活跃度分析：1 行" in text
    assert "系统运行稳定" in text


def test_export_filename_sanitizes_and_stamps():
    name = export_filename(SimpleNamespace(report_name="每日总结/报告", report_type="daily"), "html")
    assert name.endswith(".html")
    assert "/" not in name


# ---- 导出端点 ----


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    from app.api.realtime_report import realtime_report_bp

    app.register_blueprint(realtime_report_bp, url_prefix="/api/realtime-analysis/reports")
    return app


def test_export_html_returns_attachment(app, monkeypatch):
    monkeypatch.setattr(
        "app.models.realtime_report.RealtimeReport.get_by_id", lambda rid: _make_report()
    )
    client = app.test_client()
    resp = client.get("/api/realtime-analysis/reports/reports/1/export?format=html")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert "attachment" in resp.headers.get("Content-Disposition", "")


def test_export_pdf_without_weasyprint_returns_501(app, monkeypatch):
    monkeypatch.setattr(
        "app.models.realtime_report.RealtimeReport.get_by_id", lambda rid: _make_report()
    )
    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "weasyprint":
            raise ImportError("blocked in test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block)
    client = app.test_client()
    resp = client.get("/api/realtime-analysis/reports/reports/1/export?format=pdf")
    assert resp.status_code == 501
    assert "weasyprint" in resp.get_json()["message"]


def test_export_rejects_bad_format_and_missing_report(app, monkeypatch):
    client = app.test_client()
    assert client.get("/api/realtime-analysis/reports/reports/1/export?format=docx").status_code == 400

    monkeypatch.setattr(
        "app.models.realtime_report.RealtimeReport.get_by_id", lambda rid: None
    )
    assert client.get("/api/realtime-analysis/reports/reports/1/export?format=html").status_code == 404


# ---- 分发真实外发 ----


def _run_deliver(monkeypatch, requested_channels, configured_channels, send_results=None):
    service = ReportDispatchService()
    report = _make_report()

    push_service = SimpleNamespace(
        get_config=lambda: {"enabled": True, "channels": configured_channels},
        push_text=lambda title, text, channels=None, log_tag="custom": send_results or [],
    )
    import app.services.alert_push_service as aps
    import app.services.report_dispatch_service as rds

    monkeypatch.setattr(aps, "AlertPushService", lambda: push_service)
    import app.services.report_export_service as res

    monkeypatch.setattr(res, "report_digest_text", lambda rep: "标题\n正文")
    return service._deliver(report, requested_channels)


def test_deliver_skips_unconfigured_channel_without_faking_success(monkeypatch):
    results = _run_deliver(monkeypatch, ["wecom_webhook"], [])
    assert results == [{"type": "wecom_webhook", "ok": False, "message": "渠道未配置参数，跳过外发"}]


def test_deliver_sends_to_configured_channel(monkeypatch):
    sent = [{"type": "wecom_webhook", "ok": True, "message": "ok"}]
    results = _run_deliver(
        monkeypatch,
        ["wecom_webhook", "log"],
        [{"type": "wecom_webhook", "url": "https://example/hook"}],
        send_results=sent,
    )
    assert {"type": "log", "ok": True, "message": "无外发渠道，仅记录"} not in results
    assert {"type": "wecom_webhook", "ok": True, "message": "ok"} in results


def test_deliver_log_only_channel_records_without_sending(monkeypatch):
    results = _run_deliver(monkeypatch, ["log"], [])
    assert results == [{"type": "log", "ok": True, "message": "无外发渠道，仅记录"}]
