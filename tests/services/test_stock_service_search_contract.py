from pathlib import Path


def test_stock_service_supports_search_filter_for_code_and_name():
    source = Path("app/services/stock_service.py").read_text(encoding="utf-8")

    assert "def get_stock_list(industry=None, area=None, search=None, page=1, page_size=20):" in source
    assert "StockBasic.ts_code.ilike" in source
    assert "StockBasic.symbol.ilike" in source
    assert "StockBasic.name.ilike" in source
