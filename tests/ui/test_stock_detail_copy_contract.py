from pathlib import Path


def test_stock_detail_page_avoids_automatic_loading_copy():
    html = Path("app/templates/stock_detail.html").read_text(encoding="utf-8")

    assert "当前页面展示日线历史、技术因子、资金流向、筹码分布、财务数据和公司信息，均按已入库接口结果加载。" in html
    assert "历史价格数据（日线）" in html
    assert "技术因子数据（日线）" in html
    assert "财务数据" in html
    assert "公司信息" in html
    assert "切换标签页后按当前接口返回加载" in html
    assert "原始键" not in html
    assert "COMPANY_FIELD_LABELS" in html
    assert "切换到此标签页时自动加载" not in html
    assert "stockInfo?.latest_daily?.close" not in html


def test_stock_detail_page_uses_tushare_amount_units():
    html = Path("app/templates/stock_detail.html").read_text(encoding="utf-8")

    assert "成交额(万元)" in html
    assert "formatNumber((item.amount || 0) / 10, 0)" in html
