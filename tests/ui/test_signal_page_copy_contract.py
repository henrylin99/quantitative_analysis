from pathlib import Path


def test_signal_page_marks_scope_as_current_entry_only():
    html = Path("app/templates/realtime_analysis/signals.html").read_text(encoding="utf-8")

    assert "当前页面基于已入库的 Baostock 分钟数据生成与查看信号。" in html
    assert "基于技术指标和价格行为生成智能交易信号" not in html
