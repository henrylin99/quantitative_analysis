from pathlib import Path


def test_backtest_template_does_not_use_mock_result_fallback():
    html = Path("app/templates/ml_factor/backtest.html").read_text(encoding="utf-8")

    assert "displayMockResults();" not in html
    assert "function displayMockResults()" not in html
    assert "使用模拟数据进行演示" not in html


def test_backtest_template_shows_explicit_empty_state_for_missing_chart_data():
    html = Path("app/templates/ml_factor/backtest.html").read_text(encoding="utf-8")

    assert "function renderChartEmptyState(containerId, title, message)" in html
    assert "暂无累计收益数据" in html
    assert "暂无回撤数据" in html
    assert "暂无月度收益数据" in html
    assert "暂无行业分布数据" in html
    assert "暂无收益分布数据" in html
