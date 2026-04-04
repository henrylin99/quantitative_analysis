from pathlib import Path


def test_realtime_monitor_page_marks_scope_as_current_entry():
    html = Path("app/templates/realtime_analysis/monitor.html").read_text(encoding="utf-8")

    assert "当前提供监控数据查看入口，实际展示内容以页面返回结果为准" in html
    assert "实时行情监控、板块表现、异动检测和市场情绪分析" not in html
