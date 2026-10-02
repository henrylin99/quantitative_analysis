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
        save_factor_values=lambda df: len(df),
        calculate_factor=lambda factor_id, ts_codes, start, end: pd.DataFrame({
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
    """不传 factor_ids 时：逐日截面（内置+自定义）之外还要跑 alpha191 区间批量。"""
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

    fake_engine = SimpleNamespace(
        data_reader=object(),
        save_factor_values=lambda df: 0,
        calculate_all_factors=lambda date, ts_codes: pd.DataFrame(),
    )
    monkeypatch.setattr(factor_compute, 'FactorEngine', lambda: fake_engine)
    monkeypatch.setattr(
        factor_compute, 'ParquetDataReader',
        lambda: SimpleNamespace(get_trade_dates=lambda *a, **k: ['2026-01-05']),
    )

    # computable_factors() 由真实注册表驱动；只要非空即证明批量路径被触发
    monkeypatch.setenv('DATA_JOB_START_DATE', '2026-01-01')
    monkeypatch.setenv('DATA_JOB_END_DATE', '2026-01-31')

    with pytest.raises(SystemExit) as excinfo:
        factor_compute.main()
    # 全部计算单元零产出：作业按约定判失败（防假成功）
    assert excinfo.value.code == 1
    assert recorder.calls['factor_ids'], "全部因子路径必须触发 alpha191 区间批量"
