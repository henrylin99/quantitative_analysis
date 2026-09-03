from pathlib import Path


def test_report_management_form_uses_management_scope_placeholders():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "留空则自动生成报告名称" in html
    assert "使用默认模板或选择现有模板" in html
    assert "订阅名称" in html
    assert "通知渠道" in html
