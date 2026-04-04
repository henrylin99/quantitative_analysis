from pathlib import Path


def test_homepage_marks_realtime_analysis_as_partially_available():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert "实时交易分析系统（部分能力持续整改中）" in html
    assert "分钟级数据管理、技术指标分析、交易信号生成和风险监控" not in html
    assert "当前以真实数据源和已开放入口为准" in html
