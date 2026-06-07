"""Pattern screen API contract tests."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_service():
    """Mock the singleton getter for API tests."""
    svc = MagicMock()
    svc.get_groups.return_value = [
        {
            "id": "trend_structure",
            "label": "趋势结构",
            "fields": [
                {"key": "pattern_golden_cross", "label": "均线金叉", "count": 304},
                {"key": "pattern_ma_bull", "label": "均线多头排列", "count": 259},
            ],
        }
    ]
    svc.screen.return_value = {
        "total": 2,
        "offset": 0,
        "limit": 50,
        "trade_date": "20260605",
        "rows": [
            {"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行",
             "pct_chg": 1.5, "close": 12.5, "amount": 1000000,
             "total_mv": 2400000, "turnover_rate": 1.2, "vol_ratio_5": 1.8},
            {"ts_code": "000003.SZ", "name": "国农科技", "industry": "综合",
             "pct_chg": 3.0, "close": 25.0, "amount": 200000,
             "total_mv": 600000, "turnover_rate": 2.5, "vol_ratio_5": 2.1},
        ],
    }

    patcher = patch(
        'app.services.pattern_screen_service.get_pattern_screen_service',
        return_value=svc,
    )
    patcher.start()
    yield svc
    patcher.stop()


class TestGetGroups:
    def test_returns_200(self, client, mock_service):
        resp = client.get('/api/pattern-screen/groups')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200
        assert isinstance(data['data'], list)

    def test_group_structure(self, client, mock_service):
        resp = client.get('/api/pattern-screen/groups')
        data = resp.get_json()['data']
        g = data[0]
        assert 'id' in g
        assert 'label' in g
        assert 'fields' in g


class TestScreen:
    def test_returns_200(self, client, mock_service):
        resp = client.post('/api/pattern-screen/screen',
                           json={'patterns': ['pattern_golden_cross']})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200
        assert data['data']['total'] == 2

    def test_empty_patterns(self, client, mock_service):
        resp = client.post('/api/pattern-screen/screen', json={})
        assert resp.status_code == 200

    def test_invalid_sort_by_returns_400(self, client, mock_service):
        mock_service.screen.side_effect = ValueError("sort_by 'bad' not in whitelist")
        resp = client.post('/api/pattern-screen/screen',
                           json={'sort_by': 'bad'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 400

    def test_response_format(self, client, mock_service):
        resp = client.post('/api/pattern-screen/screen',
                           json={'patterns': ['pattern_golden_cross']})
        data = resp.get_json()['data']
        assert 'total' in data
        assert 'offset' in data
        assert 'limit' in data
        assert 'trade_date' in data
        assert 'rows' in data
        row = data['rows'][0]
        for col in ['ts_code', 'name', 'industry', 'pct_chg', 'close',
                     'amount', 'total_mv', 'turnover_rate', 'vol_ratio_5']:
            assert col in row
