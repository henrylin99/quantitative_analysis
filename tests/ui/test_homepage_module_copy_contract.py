from pathlib import Path


def test_homepage_marks_analysis_module_as_limited_scope():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert "基于真实返回结果查看模型与因子分析，管理能力持续整改中" in html
    assert "模型性能分析和因子有效性评估" not in html
