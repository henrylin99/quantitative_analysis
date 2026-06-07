"""PatternScreenService unit tests."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    """Minimal DataFrame mimicking data/data.parquet structure."""
    return pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000003.SZ', '000004.SZ'],
        'name': ['平安银行', '万科A', '国农科技', '国信证券'],
        'industry': ['银行', '房地产', '综合', '证券'],
        'trade_date': ['20260605'] * 4,
        'pct_chg': [1.5, -0.5, 3.0, 0.0],
        'close': [12.5, 8.0, 25.0, 15.0],
        'amount': [1000000, 500000, 200000, 300000],
        'total_mv': [2400000, 1200000, 600000, 900000],
        'turnover_rate': [1.2, 0.8, 2.5, 0.5],
        'vol_ratio_5': [1.8, 0.6, 2.1, 0.9],
        'consec_up_days': [2, 0, 3, 1],
        'pattern_golden_cross': [1, 0, 1, 0],
        'pattern_ma_bull': [0, 0, 1, 1],
        'pattern_bull_candle': [1, 0, 1, 0],
        'pattern_bear_candle': [0, 1, 0, 1],
        'break_high_20': [1, 0, 1, 0],
    })


@pytest.fixture
def service(sample_df):
    """Service with injected test DataFrame."""
    with patch('app.services.pattern_screen_service.PatternScreenService._load_df', return_value=sample_df):
        from app.services.pattern_screen_service import PatternScreenService
        svc = PatternScreenService()
        svc._df = sample_df
        return svc


class TestGetGroups:
    def test_returns_groups_with_hits(self, service):
        groups = service.get_groups()
        assert isinstance(groups, list)
        assert len(groups) > 0
        g = groups[0]
        assert 'id' in g
        assert 'label' in g
        assert 'fields' in g
        for f in g['fields']:
            assert 'key' in f
            assert 'label' in f
            assert 'count' in f
            assert isinstance(f['count'], int)

    def test_fields_not_in_dataframe_are_excluded(self, service):
        groups = service.get_groups()
        df_cols = set(service._df.columns)
        for g in groups:
            for f in g['fields']:
                assert f['key'] in df_cols


class TestScreen:
    def test_no_patterns_returns_all(self, service, sample_df):
        result = service.screen(patterns=[])
        assert result['total'] == len(sample_df)
        assert len(result['rows']) == len(sample_df)

    def test_single_pattern_filters(self, service):
        result = service.screen(patterns=['pattern_golden_cross'])
        assert result['total'] == 2
        codes = [r['ts_code'] for r in result['rows']]
        assert '000001.SZ' in codes
        assert '000003.SZ' in codes

    def test_multiple_patterns_and_logic(self, service):
        result = service.screen(patterns=['pattern_golden_cross', 'pattern_ma_bull'])
        assert result['total'] == 1
        assert result['rows'][0]['ts_code'] == '000003.SZ'

    def test_sort_desc(self, service):
        result = service.screen(patterns=[], sort_by='pct_chg', order='desc')
        pcts = [r['pct_chg'] for r in result['rows']]
        assert pcts == sorted(pcts, reverse=True)

    def test_sort_asc(self, service):
        result = service.screen(patterns=[], sort_by='pct_chg', order='asc')
        pcts = [r['pct_chg'] for r in result['rows']]
        assert pcts == sorted(pcts)

    def test_pagination(self, service):
        result = service.screen(patterns=[], limit=2, offset=0)
        assert len(result['rows']) == 2
        assert result['limit'] == 2
        assert result['offset'] == 0
        assert result['total'] == 4

    def test_offset_beyond_results(self, service):
        result = service.screen(patterns=[], offset=100)
        assert result['total'] == 4
        assert len(result['rows']) == 0

    def test_invalid_sort_by_raises(self, service):
        with pytest.raises(ValueError, match='sort_by'):
            service.screen(patterns=[], sort_by='invalid_column')

    def test_invalid_order_raises(self, service):
        with pytest.raises(ValueError, match='order'):
            service.screen(patterns=[], order='random')

    def test_invalid_pattern_key_raises(self, service):
        with pytest.raises(ValueError, match='pattern.*not found'):
            service.screen(patterns=['nonexistent_pattern'])

    def test_limit_capped_at_500(self, service):
        result = service.screen(patterns=[], limit=9999)
        assert result['limit'] == 500

    def test_includes_trade_date(self, service):
        result = service.screen(patterns=[])
        assert result['trade_date'] == '20260605'

    def test_nan_converted_to_none(self, sample_df):
        sample_df.loc[0, 'industry'] = np.nan
        with patch('app.services.pattern_screen_service.PatternScreenService._load_df', return_value=sample_df):
            from app.services.pattern_screen_service import PatternScreenService
            svc = PatternScreenService()
            svc._df = sample_df
            result = svc.screen(patterns=[])
            # Find the row with ts_code='000001.SZ' (index 0 in original df)
            row = next(r for r in result['rows'] if r['ts_code'] == '000001.SZ')
            assert row['industry'] is None


class TestInvalidateCache:
    def test_clears_df(self, service):
        assert service._df is not None
        service.invalidate_cache()
        assert service._df is None
