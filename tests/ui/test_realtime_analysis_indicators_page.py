from pathlib import Path


def test_indicators_template_renders_latest_value_and_empty_state_paths():
    html = Path("app/templates/realtime_analysis/indicators.html").read_text(encoding="utf-8")

    assert "function renderValueList" in html
    assert "data.latest_values" in html
    assert "data.indicator_summary" in html
    assert "data.empty_state" in html
    # Empty state message (no trailing period in current template)
    assert "暂无可绘制的数据" in html
