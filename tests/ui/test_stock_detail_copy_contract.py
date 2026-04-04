from pathlib import Path


def test_stock_detail_page_avoids_automatic_loading_copy():
    html = Path("app/templates/stock_detail.html").read_text(encoding="utf-8")

    assert "切换标签页后按当前接口返回加载" in html
    assert "切换到此标签页时自动加载" not in html
