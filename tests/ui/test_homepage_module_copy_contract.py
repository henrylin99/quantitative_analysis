from pathlib import Path


def test_homepage_marks_analysis_module_as_limited_scope():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert "基于真实返回结果查看模型与因子分析，管理能力持续整改中" in html
    assert "模型性能分析和因子有效性评估" not in html


def test_homepage_banner_and_query_card_avoid_platform_level_claims():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert "当前页面汇总已接通的股票分析与量化入口" in html
    assert "自然语言转 SQL 查询入口，结果以当前数据库与规则为准" in html
    assert "专业股票分析平台" not in html
    assert "AI助手" not in html
