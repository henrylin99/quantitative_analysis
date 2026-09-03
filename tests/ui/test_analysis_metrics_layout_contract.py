from pathlib import Path


def test_analysis_metrics_use_four_column_desktop_layout():
    html = Path("app/templates/analysis.html").read_text(encoding="utf-8")

    assert html.count('class="col-lg-3 col-md-6"') >= 4
