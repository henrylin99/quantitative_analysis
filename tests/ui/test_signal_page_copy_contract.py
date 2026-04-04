from pathlib import Path


def test_signal_page_marks_scope_as_current_entry_only():
    html = Path("app/templates/realtime_analysis/signals.html").read_text(encoding="utf-8")

    assert "当前提供信号生成、融合、监控与回测入口，具体结果以后端实际返回为准" in html
    assert "基于技术指标和价格行为生成智能交易信号" not in html
