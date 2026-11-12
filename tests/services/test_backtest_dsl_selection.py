"""BacktestEngine._dsl_selection 分支：DSL 解析 → 截面 → rank_stocks 输出同构。"""
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.backtest_engine import BacktestEngine


@pytest.fixture()
def engine(monkeypatch):
    engine = BacktestEngine.__new__(BacktestEngine)

    cross = pd.DataFrame({
        'momentum_20': [0.01, 0.02, 0.03, 0.04],
        'pe_percentile': [0.9, 0.7, 0.3, 0.1],
    }, index=['A', 'B', 'C', 'D'])

    class _Scoring:
        def calculate_factor_scores(self, trade_date, factor_list):
            return cross[cross.columns.intersection(factor_list)]

        def rank_stocks(self, scores_df, top_n, filters=None):
            return [
                {'ts_code': r['ts_code'], 'composite_score': r['composite_score']}
                for _, r in scores_df.iterrows()
            ]

    monkeypatch.setattr(engine, '_get_scoring_engine', lambda: _Scoring())
    return engine


def test_dsl_selection_filter_and_order(engine):
    config = {
        'selection_method': 'dsl_rule',
        'dsl': {
            'filter': 'pe_percentile < 0.5',
            'order_by': 'rank(momentum_20)',
        },
        'factor_list': ['momentum_20', 'pe_percentile'],
        'top_n': 10,
    }
    out = engine._get_stock_selection(config, '2026-01-05')
    assert [row['ts_code'] for row in out] == ['D', 'C']  # 低 PE 过滤 + 高动量降序


def test_dsl_selection_empty_filter_matches_all(engine):
    config = {
        'selection_method': 'dsl_rule',
        'dsl': {'filter': '', 'order_by': '-pe_percentile'},
        'factor_list': ['pe_percentile'],
        'top_n': 2,
    }
    out = engine._get_stock_selection(config, '2026-01-05')
    assert [row['ts_code'] for row in out] == ['D', 'C']  # -pe 降序 = 低 PE 优先


def test_dsl_selection_bad_dsl_returns_empty(engine):
    config = {
        'selection_method': 'dsl_rule',
        'dsl': {'filter': 'pe_percentile ~', 'order_by': 'pe_percentile'},
        'factor_list': ['pe_percentile'],
        'top_n': 10,
    }
    assert engine._get_stock_selection(config, '2026-01-05') == []
