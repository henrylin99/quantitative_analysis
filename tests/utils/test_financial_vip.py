"""财务三表 vip 接口下载助手测试：报告期推导、增量窗口、权限错误映射。"""

import sys
from pathlib import Path

import pytest

UTILS_DIR = Path(__file__).resolve().parent.parent.parent / 'app' / 'utils'
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from financial_vip import (  # noqa: E402
    _fetch_period,
    quarter_periods,
    resolve_report_periods,
)


def test_quarter_periods_generates_window():
    assert quarter_periods('20250101', '20251231') == ['20250331', '20250630', '20250930', '20251231']
    assert quarter_periods('20260331', '20260822') == ['20260331', '20260630']
    assert quarter_periods('20260701', '20260929') == []


def test_resolve_periods_defaults_to_local_latest(tmp_path, monkeypatch):
    # 本地最新报告期 20260331 → 从该期（含）重拉以覆盖更正
    (tmp_path / 'income_statement' / 'year=2026' / 'month=03' / 'day=31').mkdir(parents=True)
    monkeypatch.delenv('DATA_JOB_START_DATE', raising=False)
    monkeypatch.delenv('DATA_JOB_END_DATE', raising=False)
    monkeypatch.delenv('DATA_JOB_FULL_REFRESH', raising=False)

    periods, full_refresh = resolve_report_periods('income_statement', data_dir=str(tmp_path), today='20260822')
    assert periods == ['20260331', '20260630']
    assert full_refresh is False


def test_resolve_periods_env_overrides_and_full_refresh(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_JOB_START_DATE', '2024-01-01')
    monkeypatch.setenv('DATA_JOB_END_DATE', '20241231')
    monkeypatch.delenv('DATA_JOB_FULL_REFRESH', raising=False)
    periods, _ = resolve_report_periods('balance_sheet', data_dir=str(tmp_path))
    assert periods == ['20240331', '20240630', '20240930', '20241231']

    monkeypatch.delenv('DATA_JOB_START_DATE')
    monkeypatch.setenv('DATA_JOB_FULL_REFRESH', '1')
    monkeypatch.delenv('DATA_JOB_END_DATE')
    periods, full_refresh = resolve_report_periods('cash_flow', data_dir=str(tmp_path), today='20260210')
    # 全量从 2020 年第一个季度末开始
    assert periods[0] == '20200331'
    assert periods[-1] == '20251231'
    assert full_refresh is True


def test_fetch_period_maps_permission_error_with_vip_hint():
    def denied(**_kwargs):
        raise Exception('抱歉，您没有访问该接口的权限')

    with pytest.raises(ValueError) as excinfo:
        _fetch_period(denied, 'income_vip', '20260630', ['ts_code'])
    assert 'VIP' in str(excinfo.value)

    def network_error(**_kwargs):
        raise Exception('connection reset')

    with pytest.raises(Exception) as excinfo2:
        _fetch_period(network_error, 'income_vip', '20260630', ['ts_code'])
    assert 'VIP' not in str(excinfo2.value)


def test_financial_scripts_use_vip_entry_points():
    import importlib.util

    for script_name, api_name in [
        ('income_statement', 'income_vip'),
        ('balance_sheet', 'balancesheet_vip'),
        ('cash_flow', 'cashflow_vip'),
    ]:
        spec = importlib.util.spec_from_file_location(script_name, UTILS_DIR / f'{script_name}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = Path(module.__file__).read_text(encoding='utf-8')
        assert f'api_name="{api_name}"' in source, f'{script_name} 应使用 {api_name}'
        assert 'for ts_code in' not in source, f'{script_name} 不应再逐只循环'
