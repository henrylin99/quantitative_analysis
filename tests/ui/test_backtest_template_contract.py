from pathlib import Path


def test_backtest_template_does_not_use_mock_result_fallback():
    html = Path("app/templates/ml_factor/backtest.html").read_text(encoding="utf-8")

    assert "displayMockResults();" not in html
    assert "function displayMockResults()" not in html
    assert "使用模拟数据进行演示" not in html
