from pathlib import Path


def test_realtime_monitor_page_marks_scope_as_current_entry():
    html = Path("app/templates/realtime_analysis/monitor.html").read_text(encoding="utf-8")

    assert "当前页面基于已入库的 Baostock 分钟数据进行展示。" in html
    assert "实时行情监控、板块表现、异动检测和市场情绪分析" not in html
