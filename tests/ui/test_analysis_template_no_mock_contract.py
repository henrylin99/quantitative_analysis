from pathlib import Path


def test_analysis_template_does_not_use_mock_performance_defaults():
    html = Path("app/templates/ml_factor/analysis.html").read_text(encoding="utf-8")

    assert "使用模拟数据" not in html
    assert "[0.76, 0.78, 0.75, 0.73]" not in html
    assert "[0.12, 0.11, 0.13, 0.14]" not in html
    assert "['2024-01', '2024-02', '2024-03', '2024-04', '2024-05']" not in html
    assert "[0.85, 0.87, 0.86, 0.88, 0.89]" not in html
    assert "[0.72, 0.74, 0.73, 0.75, 0.76]" not in html
    assert "[0.15, 0.14, 0.15, 0.13, 0.12]" not in html
    assert "[2.5, 5.2, 3.8, 7.1, 9.3]" not in html
    assert "[1.2, 2.8, 1.5, 3.9, 4.7]" not in html
    assert "市场风险" not in html
    assert "最佳R²达到0.76" not in html


def test_analysis_template_marks_report_scope_as_limited():
    html = Path("app/templates/ml_factor/analysis.html").read_text(encoding="utf-8")

    assert "当前页面展示基于真实返回结果的分析视图，报告生成与导出能力仍较基础。" in html
    assert "<h1>📊 分析报告</h1>" not in html


def test_analysis_template_uses_neutral_best_metric_copy():
    html = Path("app/templates/ml_factor/analysis.html").read_text(encoding="utf-8")

    assert "当前最高模型R²" in html
    assert "当前最高模型 R²" in html
    assert "最佳模型R²" not in html
    assert "最佳模型 R²" not in html
