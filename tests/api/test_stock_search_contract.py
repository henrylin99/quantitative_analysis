from pathlib import Path


def test_stock_api_reads_search_query_param():
    source = Path("app/api/stock_api.py").read_text(encoding="utf-8")

    assert "request.args.get('search')" in source or 'request.args.get("search")' in source
    assert "search=search" in source
