from pathlib import Path


def test_analysis_template_does_not_use_mock_performance_defaults():
    html = Path("app/templates/ml_factor/analysis.html").read_text(encoding="utf-8")

    assert "使用模拟数据" not in html
    assert "[0.76, 0.78, 0.75, 0.73]" not in html
    assert "[0.12, 0.11, 0.13, 0.14]" not in html
