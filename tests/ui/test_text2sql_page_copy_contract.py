from pathlib import Path


def test_text2sql_page_uses_entry_positioning_copy():
    html = Path("app/templates/text2sql/index.html").read_text(encoding="utf-8")

    assert "Text2SQL 查询入口" in html
    assert "当前提供自然语言转 SQL 查询入口，结果以当前数据库和规则为准" in html
    assert "智能查询助手" not in html
