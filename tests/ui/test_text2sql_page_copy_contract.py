from pathlib import Path


def test_text2sql_page_uses_entry_positioning_copy():
    html = Path("app/templates/text2sql/index.html").read_text(encoding="utf-8")

    assert "Text2SQL 查询入口" in html
    assert "当前提供自然语言转 SQL 查询入口，结果以当前数据库和规则为准" in html
    assert "智能查询助手" not in html


def test_text2sql_guide_uses_neutral_home_entry_name():
    guide = Path("docs/guides/Text2SQL功能列表.md").read_text(encoding="utf-8")

    assert "首页 Text2SQL 查询卡片 - 已添加" in guide
    assert "首页智能查询卡片 - 已添加" not in guide
