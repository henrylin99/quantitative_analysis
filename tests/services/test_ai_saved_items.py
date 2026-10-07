"""AI 工作台沉淀存储测试：看板/常用查询 CRUD、同名覆盖、工具注册。"""

from __future__ import annotations

import pytest

from app.services.ai.saved_items import AiSavedStore


@pytest.fixture()
def store(tmp_path):
    return AiSavedStore(data_dir=str(tmp_path))


class TestBoards:
    def test_save_and_list(self, store):
        store.save_board('复盘 A', '## 结论\n看多')
        saved = store.list_all()
        assert len(saved['boards']) == 1
        assert saved['boards'][0]['title'] == '复盘 A'
        assert '结论' in saved['boards'][0]['content']

    def test_same_title_replaces(self, store):
        store.save_board('复盘', 'v1')
        store.save_board('复盘', 'v2')
        saved = store.list_all()
        assert len(saved['boards']) == 1
        assert saved['boards'][0]['content'] == 'v2'

    def test_empty_content_rejected(self, store):
        with pytest.raises(ValueError):
            store.save_board('空', '   ')

    def test_delete(self, store):
        record = store.save_board('X', '内容')
        assert store.delete('boards', record['id']) is True
        assert store.delete('boards', record['id']) is False
        assert store.list_all()['boards'] == []


class TestQueries:
    def test_save_and_dedupe_by_prompt(self, store):
        store.save_query('今天涨停多少家？')
        store.save_query('今天涨停多少家？')  # 同 prompt 去重
        saved = store.list_all()
        assert len(saved['queries']) == 1
        assert saved['queries'][0]['title'] == '今天涨停多少家？'[:30]

    def test_delete_wrong_kind_raises(self, store):
        with pytest.raises(ValueError):
            store.delete('nope', 'x')


class TestToolRegistration:
    def test_saved_tools_registered_and_executable(self, tmp_path, monkeypatch):
        from app.services.ai import tools as tools_mod
        from app.services.ai.saved_items import AiSavedStore

        # 工具内使用默认 data_dir → 指向 DATA_DIR；这里直接断言注册与 handler 行为
        names = {t.name for t in tools_mod.AI_TOOLS}
        assert {'save_board', 'save_query', 'list_saved', 'delete_saved'} <= names

        # handler 走临时目录
        monkeypatch.setenv('DATA_DIR', str(tmp_path))
        r = tools_mod.execute_tool('save_board', {'title': 'T', 'content': 'C'}, allow_actions=True)
        assert r['ok'] is True and r['result']['saved'] is True
        saved = AiSavedStore(data_dir=str(tmp_path)).list_all()
        assert len(saved['boards']) == 1
