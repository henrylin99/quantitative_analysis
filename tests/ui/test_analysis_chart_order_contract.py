from pathlib import Path


def test_analysis_page_normalizes_chart_data_to_chronological_order():
    html = Path("app/templates/analysis.html").read_text(encoding="utf-8")

    assert "function getChronologicalHistoryData()" in html
    assert "function getChronologicalFactorsData()" in html
    assert ".sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)))" in html
