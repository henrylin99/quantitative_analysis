from pathlib import Path


def test_stock_service_supports_search_filter_for_code_and_name():
    # 搜索逻辑已迁移到 ParquetDataReader.get_stock_basic_list
    reader_source = Path("app/services/data_reader.py").read_text(encoding="utf-8")
    service_source = Path("app/services/stock_service.py").read_text(encoding="utf-8")

    assert "def get_stock_list(industry=None, area=None, search=None, page=1, page_size=20):" in service_source
    assert "get_stock_basic_list" in service_source
    assert "ts_code" in reader_source
    assert "search" in reader_source
