from pathlib import Path


def test_realtime_analysis_template_hides_mock_data_source_options():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert 'option value="mock"' not in html
    assert "模拟数据" not in html


def test_realtime_analysis_template_marks_news_push_as_unavailable():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "新闻资讯推送（未开放）" in html
    assert '<i class="fas fa-check text-success"></i> 新闻资讯推送' not in html
