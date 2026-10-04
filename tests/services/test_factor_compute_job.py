"""factor_compute 数据作业测试：alpha191 批量路由与普通因子逐因子计算。"""

import importlib
import os
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture()
def factor_compute(monkeypatch):
    """导入被测脚本模块（幂等），并隔离环境变量。"""
    for name in ('DATA_JOB_TRADE_DATE', 'DATA_JOB_START_DATE', 'DATA_JOB_END_DATE',
                 'DATA_JOB_PARAM_FACTOR_IDS', 'DATA_JOB_PARAM_TS_CODES'):
        monkeypatch.delenv(name, raising=False)
    import app.utils.factor_compute as mod
    return importlib.reload(mod)


class _Recorder:
    def __init__(self):
        self.calls = {}


def test_alpha_and_custom_factors_route_to_batch_and_per_factor(factor_compute, monkeypatch, capsys):
    recorder = _Recorder()

    class FakeAlphaService:
        def __init__(self, data_reader):
            recorder.calls['data_reader'] = data_reader

        def calculate_many(self, factor_ids, start_date, end_date,
                           ts_codes=None, on_result=None, collect_results=True):
            recorder.calls.update(
                factor_ids=list(factor_ids),
                start_date=start_date,
                end_date=end_date,
                ts_codes=ts_codes,
                collect_results=collect_results,
            )
            on_result('alpha_001', pd.DataFrame({
                'ts_code': ['000001.SZ'],
                'trade_date': ['2026-01-05'],
                'factor_id': ['alpha_001'],
                'factor_value': [0.5],
            }))
            return {'alpha_001': 1}

    monkeypatch.setattr(
        'app.services.alpha191_factor_service.Alpha191FactorService', FakeAlphaService
    )

    fake_engine = SimpleNamespace(
        data_reader=object(),
        save_factor_values=lambda df, replace_factor_ids=None: len(df),
        calculate_factor=lambda factor_id, ts_codes, start, end, data_cache=None: pd.DataFrame({
            'ts_code': ['000001.SZ'],
            'trade_date': ['2026-01-05'],
            'factor_id': [factor_id],
            'factor_value': [1.0],
        }),
    )
    monkeypatch.setattr(factor_compute, 'FactorEngine', lambda: fake_engine)
    monkeypatch.setattr(
        factor_compute, 'ParquetDataReader', SimpleNamespace
    )  # 全部因子路径才会用到；本用例传了 factor_ids，不应实例化

    monkeypatch.setenv('DATA_JOB_START_DATE', '2026-01-01')
    monkeypatch.setenv('DATA_JOB_END_DATE', '2026-01-31')
    monkeypatch.setenv('DATA_JOB_PARAM_FACTOR_IDS', 'alpha_001,ma_cross')

    factor_compute.main()

    out = capsys.readouterr().out
    # alpha191 走批量接口：面板共享一次加载 + collect_results=False 防内存驻留
    assert recorder.calls['factor_ids'] == ['alpha_001']
    assert recorder.calls['collect_results'] is False
    assert recorder.calls['start_date'] == '2026-01-01'
    # 普通因子走逐因子区间计算并落库
    assert '共写入 2 条' in out
    assert 'ma_cross' in str(recorder.calls) or 'ma_cross' in out


def test_all_factors_path_includes_alpha_batch(factor_compute, monkeypatch, capsys):
    """不传 factor_ids 的区间模式：逐因子整段路径之外还要跑 alpha191 区间批量。"""
    recorder = _Recorder()

    class FakeAlphaService:
        def __init__(self, data_reader):
            pass

        def calculate_many(self, factor_ids, start_date, end_date,
                           ts_codes=None, on_result=None, collect_results=True):
            recorder.calls['factor_ids'] = list(factor_ids)
            return {}

    per_factor_calls = []

    def fake_calculate_factor(factor_id, ts_codes, start, end, data_cache=None):
        per_factor_calls.append(factor_id)
        return pd.DataFrame()

    monkeypatch.setattr(
        'app.services.alpha191_factor_service.Alpha191FactorService', FakeAlphaService
    )

    fake_engine = SimpleNamespace(
        data_reader=object(),
        save_factor_values=lambda df: 0,
        builtin_factors={'momentum_1d': object(), 'alpha_001': object()},
        factor_definitions={'custom_ma': object()},
        calculate_factor=fake_calculate_factor,
        calculate_all_factors=lambda date, ts_codes: pd.DataFrame(),
    )
    monkeypatch.setattr(factor_compute, 'FactorEngine', lambda: fake_engine)
    monkeypatch.setattr(
        factor_compute, 'ParquetDataReader',
        lambda: SimpleNamespace(get_trade_dates=lambda *a, **k: ['2026-01-05']),
    )
    # 覆盖扫描已有独立用例；这里返回空覆盖，确保批量路径仍被全量触发
    monkeypatch.setattr(
        factor_compute, '_scan_factor_coverage',
        lambda engine, start, end: ({}, {}),
    )

    # computable_factors() 由真实注册表驱动；只要非空即证明批量路径被触发
    monkeypatch.setenv('DATA_JOB_START_DATE', '2026-01-01')
    monkeypatch.setenv('DATA_JOB_END_DATE', '2026-01-31')

    with pytest.raises(SystemExit) as excinfo:
        factor_compute.main()
    # 全部计算单元零产出：作业按约定判失败（防假成功）
    assert excinfo.value.code == 1
    assert recorder.calls['factor_ids'], "全部因子路径必须触发 alpha191 区间批量"
    # 区间模式逐因子整段计算：内置非 alpha + 自定义走 calculate_factor，
    # alpha191 已由批量路径覆盖、不重复进入
    assert per_factor_calls == ['momentum_1d', 'custom_ma']


def test_single_day_mode_keeps_cross_section_path(factor_compute, monkeypatch, capsys):
    """单日模式（START == END）：仍按日截面走 calculate_all_factors。"""
    recorder = _Recorder()

    class FakeAlphaService:
        def __init__(self, data_reader):
            pass

        def calculate_many(self, factor_ids, start_date, end_date,
                           ts_codes=None, on_result=None, collect_results=True):
            recorder.calls['factor_ids'] = list(factor_ids)
            return {}

    per_factor_calls = []

    monkeypatch.setattr(
        'app.services.alpha191_factor_service.Alpha191FactorService', FakeAlphaService
    )

    fake_engine = SimpleNamespace(
        data_reader=object(),
        save_factor_values=lambda df, replace_factor_ids=None: True,
        builtin_factors={'momentum_1d': object()},
        factor_definitions={},
        calculate_factor=lambda factor_id, ts_codes, start, end, data_cache=None: (
            per_factor_calls.append(factor_id) or pd.DataFrame()
        ),
        calculate_all_factors=lambda date, ts_codes: pd.DataFrame({
            'ts_code': ['000001.SZ'],
            'trade_date': [date],
            'factor_id': ['momentum_1d'],
            'factor_value': [1.0],
        }),
    )
    monkeypatch.setattr(factor_compute, 'FactorEngine', lambda: fake_engine)
    monkeypatch.setattr(
        factor_compute, 'ParquetDataReader',
        lambda: SimpleNamespace(get_trade_dates=lambda *a, **k: ['2026-01-05']),
    )

    monkeypatch.setenv('DATA_JOB_TRADE_DATE', '2026-01-05')

    factor_compute.main()

    out = capsys.readouterr().out
    assert '共写入 1 条' in out
    # 单日截面路径生效，逐因子路径不应触发
    assert per_factor_calls == []


def test_range_backfill_skips_covered_alpha_factors(factor_compute, monkeypatch, capsys):
    """区间全市场回填：已有覆盖的 alpha 跳过重算，缺口因子照常进批量。"""
    from app.services.alpha191_factor_service import computable_factors

    recorder = _Recorder()

    class FakeAlphaService:
        def __init__(self, data_reader):
            pass

        def calculate_many(self, factor_ids, start_date, end_date,
                           ts_codes=None, on_result=None, collect_results=True):
            recorder.calls['factor_ids'] = list(factor_ids)
            return {}

    monkeypatch.setattr(
        'app.services.alpha191_factor_service.Alpha191FactorService', FakeAlphaService
    )

    all_alphas = sorted(computable_factors())
    dates = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08']
    # 只有 alpha_001 在库内全覆盖；alpha_002 仅 1 天；其余因子无任何覆盖
    cov = {
        'alpha_001': {'covered': len(dates), 'first': dates[0], 'last': dates[-1]},
        'alpha_002': {'covered': 1, 'first': dates[0], 'last': dates[0]},
    }
    monkeypatch.setattr(
        factor_compute, '_scan_factor_coverage',
        lambda engine, start, end: (cov, {d: len(all_alphas) for d in dates}),
    )

    fake_engine = SimpleNamespace(
        data_reader=object(),
        save_factor_values=lambda df, replace_factor_ids=None: True,
        builtin_factors={},
        factor_definitions={},
        calculate_factor=lambda *a, **k: pd.DataFrame(),
        calculate_all_factors=lambda date, ts_codes: pd.DataFrame(),
    )
    monkeypatch.setattr(factor_compute, 'FactorEngine', lambda: fake_engine)
    monkeypatch.setattr(
        factor_compute, 'ParquetDataReader',
        lambda: SimpleNamespace(get_trade_dates=lambda *a, **k: dates),
    )

    monkeypatch.setenv('DATA_JOB_START_DATE', '2026-01-05')
    monkeypatch.setenv('DATA_JOB_END_DATE', '2026-01-08')

    with pytest.raises(SystemExit) as excinfo:
        factor_compute.main()

    # 剩余因子全零产出：作业按约定判失败（防假成功）
    assert excinfo.value.code == 1
    assert 'alpha_001' not in recorder.calls['factor_ids']
    assert 'alpha_002' in recorder.calls['factor_ids']
    assert len(recorder.calls['factor_ids']) == len(all_alphas) - 1
    out = capsys.readouterr().out
    assert 'skip: 已覆盖 4/4 天' in out


def _frame(factor_id, value=1.0, date='2026-01-05'):
    return pd.DataFrame({
        'ts_code': ['000001.SZ'],
        'trade_date': [date],
        'factor_id': [factor_id],
        'factor_value': [value],
    })


def test_bulk_saver_buffers_across_factors_and_flushes_once(factor_compute):
    """跨因子缓冲：攒够行数才落盘，且按 factor_id 整体替换合并。"""
    calls = []

    class FakeEngine:
        def save_factor_values(self, df, replace_factor_ids=None):
            calls.append({
                'rows': len(df),
                'factors': sorted(df['factor_id'].astype(str).unique()),
                'replace': sorted(replace_factor_ids or []),
            })
            return True

    saver = factor_compute._BulkSaver(FakeEngine(), flush_rows=3)
    for index in range(3):
        saver.add(f'f{index}', _frame(f'f{index}', value=float(index)))

    assert len(calls) == 1  # 第三个因子触发阈值 flush
    assert calls[0]['rows'] == 3
    assert calls[0]['factors'] == ['f0', 'f1', 'f2']
    assert calls[0]['replace'] == ['f0', 'f1', 'f2']
    assert saver.written == 3

    saver.flush()  # 缓冲已空：无重复落盘
    assert len(calls) == 1


def test_bulk_saver_failure_marks_buffer_and_recovers(factor_compute):
    """落盘失败的缓冲组丢弃不重放，后续因子照常写入。"""

    class FlakyEngine:
        def __init__(self):
            self.ok = False
            self.calls = []

        def save_factor_values(self, df, replace_factor_ids=None):
            self.calls.append(len(df))
            return self.ok

    engine = FlakyEngine()
    saver = factor_compute._BulkSaver(engine)
    saver.add('f0', _frame('f0'))

    with pytest.raises(RuntimeError):
        saver.flush()
    assert saver.last_failed_ids == ['f0']
    assert saver.written == 0

    engine.ok = True
    saver.add('f1', _frame('f1', date='2026-01-06'))
    saver.flush()
    assert saver.written == 1
    assert engine.calls == [1, 1]
