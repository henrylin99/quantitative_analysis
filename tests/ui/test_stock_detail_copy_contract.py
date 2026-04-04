from pathlib import Path


def test_stock_detail_page_avoids_automatic_loading_copy():
    html = Path("app/templates/stock_detail.html").read_text(encoding="utf-8")

    assert "当前页面展示日线历史、技术因子、资金流向和筹码分布数据，均按已入库接口结果加载。" in html
    assert "历史价格数据（日线）" in html
    assert "技术因子数据（日线）" in html
    assert "切换标签页后按当前接口返回加载" in html
    assert "切换到此标签页时自动加载" not in html
    assert "stockInfo?.latest_daily?.close" not in html
