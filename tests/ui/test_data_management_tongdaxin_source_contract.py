from pathlib import Path


def test_data_management_page_defaults_minute_source_to_tongdaxin():
    html = Path("app/templates/data_management/index.html").read_text(encoding="utf-8")

    assert '<option value="tongdaxin" selected>通达信</option>' in html
    assert "Baostock 不能拉取当天实时分钟数据" in html
