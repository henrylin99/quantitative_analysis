"""策略 DSL 解析器与求值测试：词表校验、NaN 语义、排序可复现性。"""
import numpy as np
import pandas as pd
import pytest

from app.services.strategy_dsl import DslError, parse_dsl

KNOWN = {'momentum_20', 'pe_percentile', 'turnover_rate'}


def _cross_section() -> pd.DataFrame:
    # 6 只票的合成截面：momentum 递增，pe 递减，含 NaN
    return pd.DataFrame({
        'momentum_20': [0.01, 0.02, 0.03, 0.04, 0.05, np.nan],
        'pe_percentile': [0.9, 0.7, 0.5, 0.3, 0.1, 0.4],
        'turnover_rate': [5.0, 8.0, 12.0, 15.0, 20.0, 10.0],
    }, index=['A', 'B', 'C', 'D', 'E', 'F'])


class TestParse:
    def test_valid_filter_and_order(self):
        program = parse_dsl(
            'rank(momentum_20) > 0.5 and pe_percentile < 0.6',
            'rank(momentum_20) * 0.6 - rank(pe_percentile) * 0.4',
            KNOWN,
        )
        assert program.referenced_factors == {'momentum_20', 'pe_percentile'}

    def test_unknown_factor_rejected(self):
        with pytest.raises(DslError, match='未知因子'):
            parse_dsl('', 'nope_factor + 1', KNOWN)

    def test_power_operator_rejected(self):
        with pytest.raises(DslError, match='运算符'):
            parse_dsl('', 'momentum_20 ** 2', KNOWN)

    def test_order_by_boolean_rejected(self):
        with pytest.raises(DslError, match='order_by'):
            parse_dsl('', 'momentum_20 > 0.5', KNOWN)

    def test_filter_arithmetic_rejected(self):
        with pytest.raises(DslError, match='布尔'):
            parse_dsl('momentum_20 + 1', 'momentum_20', KNOWN)

    def test_unknown_function_rejected(self):
        with pytest.raises(DslError, match='函数'):
            parse_dsl('', 'log(momentum_20)', KNOWN)

    def test_quantile_args_validated(self):
        with pytest.raises(DslError, match='quantile'):
            parse_dsl('', 'quantile(momentum_20)', KNOWN)
        with pytest.raises(DslError, match='quantile'):
            parse_dsl('', 'quantile(momentum_20, 1)', KNOWN)
        parse_dsl('quantile(momentum_20, 5) == 4', 'momentum_20', KNOWN)

    def test_chain_comparison_rejected(self):
        with pytest.raises(DslError, match='链式'):
            parse_dsl('0.2 < pe_percentile < 0.8', 'pe_percentile', KNOWN)

    def test_syntax_error_wrapped(self):
        with pytest.raises(DslError, match='语法错误'):
            parse_dsl('momentum_20 >', 'momentum_20', KNOWN)

    def test_empty_order_by_rejected(self):
        with pytest.raises(DslError, match='order_by'):
            parse_dsl('momentum_20 > 0', '', KNOWN)

    def test_depth_limit(self):
        deep = 'momentum_20' + ' + momentum_20' * 12  # 12 层嵌套仍合法
        parse_dsl('', deep, KNOWN)
        too_deep = deep + ' + momentum_20'
        with pytest.raises(DslError, match='嵌套'):
            parse_dsl('', too_deep, KNOWN)

    def test_not_and_or(self):
        program = parse_dsl(
            'not (pe_percentile > 0.5) or turnover_rate > 18',
            'momentum_20', KNOWN,
        )
        assert 'turnover_rate' in program.referenced_factors


class TestSelect:
    def test_filter_nan_rows_excluded(self):
        program = parse_dsl('momentum_20 > 0', 'momentum_20', KNOWN)
        out = program.select(_cross_section(), 10)
        assert 'F' not in set(out['ts_code'])  # momentum NaN 被剔除

    def test_order_descending_and_top_n(self):
        program = parse_dsl('', 'momentum_20', KNOWN)
        out = program.select(_cross_section(), 3)
        assert list(out['ts_code']) == ['E', 'D', 'C']
        assert out['rank'].tolist() == [1, 2, 3]

    def test_rank_direction_ascending(self):
        # rank 升序：pe 越小 rank 越小 → -rank(pe) 降序 = 低 PE 优先
        program = parse_dsl('', '-rank(pe_percentile)', KNOWN)
        out = program.select(_cross_section(), 2)
        assert list(out['ts_code']) == ['E', 'D']

    def test_filter_plus_order_combo(self):
        program = parse_dsl(
            'rank(momentum_20) > 0.5 and turnover_rate < 16',
            'rank(momentum_20) - rank(pe_percentile)', KNOWN,
        )
        out = program.select(_cross_section(), 10)
        # rank(mom)>0.5: C/D/E (F 已 NaN)；turnover<16: A~D → 交集成 C/D
        assert set(out['ts_code']) == {'C', 'D'}

    def test_ties_reproducible_by_ts_code(self):
        df = pd.DataFrame({'x': [1.0, 1.0, 1.0]}, index=['C', 'A', 'B'])
        program = parse_dsl('', 'x', {'x'})
        out = program.select(df, 10)
        assert list(out['ts_code']) == ['A', 'B', 'C']

    def test_empty_cross_section(self):
        program = parse_dsl('', 'momentum_20', KNOWN)
        assert program.select(pd.DataFrame(), 5).empty

    def test_filter_excludes_all_returns_empty(self):
        program = parse_dsl('momentum_20 > 99', 'momentum_20', KNOWN)
        assert program.select(_cross_section(), 5).empty

    def test_result_shape_for_rank_stocks(self):
        program = parse_dsl('', 'momentum_20', KNOWN)
        out = program.select(_cross_section(), 5)
        assert {'ts_code', 'composite_score', 'rank', 'percentile_rank'} <= set(out.columns)

    def test_zscore_std_zero_returns_zeros(self):
        df = pd.DataFrame({'x': [5.0, 5.0, 5.0]}, index=['A', 'B', 'C'])
        program = parse_dsl('', 'zscore(x)', {'x'})
        out = program.select(df, 3)
        assert (out['composite_score'] == 0).all()

    def test_quantile_bucketing(self):
        program = parse_dsl('quantile(momentum_20, 5) == 4', 'momentum_20', KNOWN)
        out = program.select(_cross_section(), 10)
        assert list(out['ts_code']) == ['E']  # 最高桶
