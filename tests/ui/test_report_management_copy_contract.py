from pathlib import Path


def test_report_management_form_uses_current_scope_placeholders():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "留空则由当前页面按规则补全" in html
    assert "使用当前已接入模板" in html
    assert "留空自动生成" not in html
    assert "使用默认模板" not in html
