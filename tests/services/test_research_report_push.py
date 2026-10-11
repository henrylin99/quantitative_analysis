"""研报推送激活（批次 2.2）：自选股当日研报 → news payload，按 info_code 去重。"""

import json

import pytest

from app.services.websocket_push_service import WebSocketPushService


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    return WebSocketPushService()


def _patch_research(monkeypatch, items_by_code):
    """替换研报服务与自选股来源。"""
    import app.services.research_report_service as rrs
    import app.services.watchlist_service as ws

    class _FakeService:
        def search_reports(self, category, code=None, begin=None, end=None, **kwargs):
            return {'items': items_by_code.get(code, [])}

    monkeypatch.setattr(rrs, 'get_research_report_service', lambda: _FakeService())
    monkeypatch.setattr(
        ws.WatchlistService, 'list_items',
        lambda self: [{'ts_code': c} for c in items_by_code],
    )


def _report(info_code, title='某公司深度报告'):
    return {
        'info_code': info_code,
        'title': title,
        'stock_code': '000001',
        'stock_name': '平安银行',
        'org_name': '某某证券',
        'publish_date': '2026-10-11',
        'rating': '买入',
        'detail_url': f'https://data.eastmoney.com/report/info/{info_code}.html',
    }


def test_news_payload_returns_watchlist_research_reports(service, monkeypatch):
    _patch_research(monkeypatch, {'000001.SZ': [_report('AP202610110001')]})

    items = service._get_news_payload()
    assert len(items) == 1
    assert items[0]['type'] == 'research_report'
    assert items[0]['ts_code'] == '000001.SZ'
    assert items[0]['title'] == '某公司深度报告'
    assert 'eastmoney.com' in items[0]['url']


def test_news_payload_dedupes_by_info_code_across_calls(service, monkeypatch):
    _patch_research(monkeypatch, {'000001.SZ': [_report('AP202610110001')]})

    assert len(service._get_news_payload()) == 1
    # 同一批研报第二次不重推
    assert service._get_news_payload() == []

    # 新研报出现后才再推，且旧 id 仍在去重集合里
    items_by_code = {
        '000001.SZ': [_report('AP202610110001'), _report('AP202610110002', '新报告')]
    }
    _patch_research(monkeypatch, items_by_code)
    items = service._get_news_payload()
    assert [it['title'] for it in items] == ['新报告']


def test_news_payload_survives_restart_with_persisted_seen(service, monkeypatch, tmp_path):
    _patch_research(monkeypatch, {'000001.SZ': [_report('AP202610110001')]})
    service._get_news_payload()

    seen_file = tmp_path / 'research_push' / 'seen.json'
    assert seen_file.exists()
    assert json.loads(seen_file.read_text()) == ['AP202610110001']

    # 新实例（模拟重启）读到落盘去重记录，不重推
    second = WebSocketPushService()
    assert second._get_news_payload() == []


def test_news_payload_empty_watchlist_returns_empty(service, monkeypatch):
    _patch_research(monkeypatch, {})
    assert service._get_news_payload() == []


def test_news_payload_swallows_report_fetch_errors(service, monkeypatch):
    import app.services.research_report_service as rrs
    import app.services.watchlist_service as ws

    class _FailingService:
        def search_reports(self, *args, **kwargs):
            raise RuntimeError('eastmoney down')

    monkeypatch.setattr(rrs, 'get_research_report_service', lambda: _FailingService())
    monkeypatch.setattr(ws.WatchlistService, 'list_items', lambda self: [{'ts_code': '000001.SZ'}])

    assert service._get_news_payload() == []
