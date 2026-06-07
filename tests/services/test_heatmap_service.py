"""Tests for HeatmapService — sector aggregation logic."""
import json
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    """Minimal DataFrame matching data/data.parquet schema."""
    return pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000003.SZ', '000004.SZ', '000005.SZ'],
        'name': ['平安银行', '万科Ａ', '测试银行', '测试地产', '停牌股'],
        'industry': ['银行', '全国地产', '银行', '全国地产', '全国地产'],
        'pct_chg': [1.5, -2.0, 0.5, -1.0, 0.0],
        'close': [11.0, 3.5, 5.0, 8.0, 0.0],
        'total_mv': [21300, 3900, 5000, 2000, 100],
        'net_mf_amount': [14000, -5000, 3000, -2000, 0],
        'turnover_rate': [0.5, 1.7, 1.0, 2.0, 0.0],
        'trade_date': ['20260605'] * 5,
    })


@pytest.fixture
def service():
    from app.services.heatmap_service import HeatmapService
    return HeatmapService()


class TestGetHeatmapData:
    """Test HeatmapService.get_heatmap_data()."""

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_returns_two_lists(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, stocks = service.get_heatmap_data()
        assert isinstance(sectors, list)
        assert isinstance(stocks, list)

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_filters_suspended_stocks(self, mock_read, service, sample_df):
        """Stocks with close == 0 should be excluded."""
        mock_read.return_value = sample_df
        sectors, stocks = service.get_heatmap_data()
        stock_names = [s['name'] for s in stocks]
        assert '停牌股' not in stock_names

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_count(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        industry_names = [s['name'] for s in sectors]
        assert len(industry_names) == 2  # 银行 + 全国地产

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_weighted_pct_chg(self, mock_read, service, sample_df):
        """avg_pct_chg should be market-cap weighted average."""
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        bank = next(s for s in sectors if s['name'] == '银行')
        # Weighted: (1.5*21300 + 0.5*5000) / (21300+5000) = 34450/26300 ≈ 1.3103
        assert abs(bank['avg_pct_chg'] - 1.3103) < 0.01

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_stock_count(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        bank = next(s for s in sectors if s['name'] == '银行')
        assert bank['stock_count'] == 2  # 2 银行 after filtering

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_up_down_count(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        realestate = next(s for s in sectors if s['name'] == '全国地产')
        assert realestate['down_count'] == 2
        assert realestate['up_count'] == 0

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_stocks_have_required_fields(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        _, stocks = service.get_heatmap_data()
        required = {'name', 'ts_code', 'pct_chg', 'close', 'total_mv',
                    'net_mf_amount', 'turnover_rate', 'industry'}
        for s in stocks:
            assert required.issubset(s.keys()), f"Missing keys: {required - s.keys()}"

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_trade_date_returned(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        assert sectors[0]['trade_date'] == '20260605'
