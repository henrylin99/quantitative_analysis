from pathlib import Path


def test_realtime_indicators_page_marks_scope_as_current_entry():
    html = Path("app/templates/realtime_analysis/indicators.html").read_text(encoding="utf-8")

    assert "当前页面基于已入库的 Baostock 分钟数据计算指标。" in html
    assert "计算和分析股票的实时技术指标，支持多周期和多指标对比分析" not in html
