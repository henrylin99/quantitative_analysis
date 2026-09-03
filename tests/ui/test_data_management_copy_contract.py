from pathlib import Path


def test_data_management_page_guides_initialization_order():
    html = Path("app/templates/data_management/index.html").read_text(encoding="utf-8")

    assert "推荐初始化顺序" in html
    assert "初始化状态" in html
    assert "dataInitializationPanel" in html
    assert "statusNextActions" in html
    assert "1. 交易日历" in html
    assert "2. 股票基础资料" in html
    assert "3. 日线行情" in html
    assert "4. 日线基本指标" in html
    assert "data-recommended-job=\"trade_calendar\"" in html
    assert "data-recommended-job=\"stock_basic\"" in html
