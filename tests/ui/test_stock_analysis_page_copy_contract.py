from pathlib import Path


def test_stock_analysis_page_avoids_professional_platform_claim():
    html = Path("app/templates/analysis.html").read_text(encoding="utf-8")

    assert "当前提供K线与技术指标查看入口，结果以实际数据返回为准" in html
    assert "专业K线图、技术指标分析" not in html
