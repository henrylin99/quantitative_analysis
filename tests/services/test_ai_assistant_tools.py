"""AI 智能工作台工具层测试：只读约束、数据查询、任务触发、因子与模式控制。"""

from types import SimpleNamespace

import pandas as pd
import pytest
from flask import Flask

import app.services.ai.tools as ai_tools
from app.services.ai.tools import execute_tool, get_tool_specs, list_tool_summaries


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, DATA_DIR=str(tmp_path))
    with app.app_context():
        yield app
    ai_tools.reset_singletons()
    from app.services.text2sql_engine import get_text2sql_engine

    get_text2sql_engine().query_executor.invalidate_cache()


def _write_stock_business(data_dir, rows):
    df = pd.DataFrame(rows)
    df.to_parquet(data_dir / 'stock_business.parquet', index=False)


def test_query_data_reads_parquet_and_enforces_readonly(app, tmp_path):
    _write_stock_business(
        tmp_path,
        [
            {'ts_code': '000001.SZ', 'trade_date': '20260601', 'close': 10.0, 'pe_ttm': 8.5},
            {'ts_code': '000002.SZ', 'trade_date': '20260601', 'close': 20.0, 'pe_ttm': 12.0},
        ],
    )

    outcome = execute_tool(
        'query_data', {'sql': 'SELECT ts_code, daily_close FROM stock_business ORDER BY daily_close'}
    )
    assert outcome['ok'] is True
    assert outcome['result']['row_count'] == 2
    assert outcome['result']['rows'][0]['ts_code'] == '000001.SZ'
    assert outcome['result']['columns'] == ['ts_code', 'daily_close']

    rejected = execute_tool('query_data', {'sql': 'DELETE FROM stock_business'})
    assert rejected['ok'] is False
    assert '只读' in rejected['error']


def test_query_data_truncates_rows_for_llm(app, tmp_path):
    _write_stock_business(
        tmp_path,
        [{'ts_code': f'{i:06d}.SZ', 'trade_date': '20260601', 'close': float(i)} for i in range(40)],
    )

    outcome = execute_tool('query_data', {'sql': 'SELECT ts_code FROM stock_business'})
    assert outcome['ok'] is True
    assert outcome['result']['row_count'] == 40
    assert len(outcome['result']['rows']) == ai_tools.MAX_ROWS_FOR_LLM
    assert outcome['result']['truncated'] is True


def test_list_data_tables_reports_tables_and_wide_status(app, tmp_path):
    _write_stock_business(
        tmp_path,
        [{'ts_code': '000001.SZ', 'trade_date': '20260601', 'close': 10.0}],
    )

    outcome = execute_tool('list_data_tables', {})
    assert outcome['ok'] is True
    tables = {t['table']: t for t in outcome['result']['query_tables']}
    assert set(tables) == {'stock_business', 'stock_factor', 'stock_moneyflow', 'stock_ma_data'}
    assert tables['stock_business']['exists'] is True
    assert tables['stock_business']['latest_trade_date'] == '20260601'
    assert 'wide_table' in outcome['result']


def test_get_table_schema_rejects_unknown_table(app):
    outcome = execute_tool('get_table_schema', {'table': 'nope'})
    assert outcome['ok'] is False
    assert 'stock_business' in outcome['error']


def test_unknown_tool_and_readonly_mode(app):
    assert execute_tool('not_a_tool', {})['ok'] is False

    blocked = execute_tool('run_data_job', {'job_type': 'trade_calendar'}, allow_actions=False)
    assert blocked['ok'] is False
    assert '只读模式' in blocked['error']

    specs = get_tool_specs(allow_actions=False)
    names = {spec['function']['name'] for spec in specs}
    assert 'query_data' in names
    assert 'run_data_job' not in names

    summaries = list_tool_summaries(allow_actions=True)
    kinds = {item['name']: item['kind'] for item in summaries}
    assert kinds['build_wide_table'] == 'action'
    assert kinds['query_data'] == 'read'


def test_run_data_job_requires_tushare_token(app, monkeypatch):
    monkeypatch.delenv('TUSHARE_TOKEN', raising=False)
    outcome = execute_tool('run_data_job', {'job_type': 'trade_calendar'})
    assert outcome['ok'] is False
    assert 'TUSHARE_TOKEN' in outcome['error']


def test_run_data_job_submits_allowed_params_only(app, monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN', 'real-token')
    captured = {}

    def fake_submit(job_type, params):
        captured['job_type'] = job_type
        captured['params'] = params
        return SimpleNamespace(
            id=7, job_type=job_type, status='queued', progress=0.0,
            progress_message='已入队', error_message=None,
        )

    fake_service = SimpleNamespace(submit=fake_submit)
    monkeypatch.setattr(ai_tools, '_get_data_job_service', lambda: fake_service)

    outcome = execute_tool(
        'run_data_job',
        {'job_type': 'daily_basic', 'params': {'start_date': '20260601', 'evil': 'rm -rf'}},
    )
    assert outcome['ok'] is True
    assert captured['job_type'] == 'daily_basic'
    assert captured['params'] == {'start_date': '20260601'}
    assert outcome['result']['run_id'] == 7


def test_list_data_tables_reports_datasets_and_increment_window(app, tmp_path):
    _write_stock_business(
        tmp_path,
        [{'ts_code': '000001.SZ', 'trade_date': '20260601', 'close': 10.0}],
    )
    # 造一个 daily_history 分区和交易日历，验证数据集目录与增量窗口信息
    (tmp_path / 'daily_history' / 'daily' / 'year=2026' / 'month=06' / 'day=05').mkdir(parents=True)
    pd.DataFrame(
        {'cal_date': ['2026-06-05', '2026-06-08'], 'is_open': [1, 1]}
    ).to_parquet(tmp_path / 'stock_trade_calendar.parquet', index=False)

    outcome = execute_tool('list_data_tables', {})
    assert outcome['ok'] is True
    datasets = {d['dataset']: d for d in outcome['result']['datasets']}
    assert datasets['daily_history']['latest_date'] == '20260605'
    assert datasets['daily_history']['job_type'] == 'daily_history_by_date'
    assert datasets['income_statement']['job_type'] == 'income_statement'
    # 增量窗口推导所需的两个关键值都在返回里
    assert 'latest_trade_date' in outcome['result']
    assert outcome['result']['latest_trade_date'] == '20260608'
    assert 'start_date' in outcome['result']['hint']


def test_run_data_jobs_batch_executes_sequentially_and_tolerates_failure(app, monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN', 'real-token')
    submitted = []

    def fake_submit(job_type, params):
        submitted.append((job_type, params))
        if job_type == 'moneyflow':
            return SimpleNamespace(
                id=len(submitted), job_type=job_type, status='failed', progress=0.0,
                progress_message='下载失败', error_message='tushare 积分不足',
            )
        return SimpleNamespace(
            id=len(submitted), job_type=job_type, status='success', progress=100.0,
            progress_message='完成', error_message=None,
        )

    fake_service = SimpleNamespace(submit=fake_submit)
    monkeypatch.setattr(ai_tools, '_get_data_job_service', lambda: fake_service)

    outcome = execute_tool(
        'run_data_jobs',
        {'job_types': ['trade_calendar', 'daily_history_by_date', 'moneyflow'], 'params': {'start_date': '20260606'}},
    )
    assert outcome['ok'] is True
    result = outcome['result']
    assert result['total'] == 3 and result['succeeded'] == 2 and result['failed'] == 1
    assert [job for job, _ in submitted] == ['trade_calendar', 'daily_history_by_date', 'moneyflow']
    assert all(params == {'start_date': '20260606'} for _, params in submitted)
    failed = next(item for item in result['results'] if not item['ok'])
    assert failed['job_type'] == 'moneyflow'

    # 空列表与非法参数被拒绝
    assert execute_tool('run_data_jobs', {'job_types': []})['ok'] is False
    assert execute_tool('run_data_jobs', {'job_types': 'daily_basic'})['ok'] is False

    # 批量工具属于动作类，只读模式下被禁用
    blocked = execute_tool('run_data_jobs', {'job_types': ['daily_basic']}, allow_actions=False)
    assert blocked['ok'] is False and '只读模式' in blocked['error']


def test_run_data_job_rejects_dangerous_and_unknown_and_wide_table(app, monkeypatch):
    monkeypatch.setenv('TUSHARE_TOKEN', 'real-token')

    dangerous = execute_tool('run_data_job', {'job_type': 'ma_calculator'})
    assert dangerous['ok'] is False
    assert '危险' in dangerous['error']

    unknown = execute_tool('run_data_job', {'job_type': 'not_exists'})
    assert unknown['ok'] is False

    redirected = execute_tool('run_data_job', {'job_type': 'wide_table_builder'})
    assert redirected['ok'] is False
    assert 'build_wide_table' in redirected['error']


def test_build_wide_table_blocked_before_cutoff(app, monkeypatch):
    fake_status = {
        'exists': True, 'wide_table_date': '2026-06-01', 'source_dates': {},
        'should_update': True, 'reason': '数据源更新', 'past_cutoff': False,
    }
    monkeypatch.setattr(
        'app.services.wide_table_status.get_wide_table_status', lambda data_dir=None: dict(fake_status)
    )
    outcome = execute_tool('build_wide_table', {})
    assert outcome['ok'] is False
    assert '18:00' in outcome['error']


def test_calculate_factors_normalizes_date_and_saves(app, monkeypatch):
    calls = {}

    class FakeEngine:
        def calculate_factor(self, factor_id, ts_codes, start_date, end_date):
            calls['single'] = (factor_id, ts_codes, start_date, end_date)
            return pd.DataFrame({'factor_id': [factor_id], 'ts_code': ['000001.SZ'], 'value': [1.0]})

        def save_factor_values(self, df):
            calls['saved'] = len(df)
            return True

    monkeypatch.setattr(ai_tools, '_get_factor_engine', lambda: FakeEngine())

    outcome = execute_tool('calculate_factors', {'trade_date': '2026-06-03', 'factor_ids': ['roe']})
    assert outcome['ok'] is True
    assert calls['single'] == ('roe', [], '2026-06-03', '2026-06-03')
    assert calls['saved'] == 1
    assert outcome['result']['results'][0]['calculated_count'] == 1

    bad_date = execute_tool('calculate_factors', {'trade_date': '2026/06/03'})
    assert bad_date['ok'] is False
    assert 'YYYY-MM-DD' in bad_date['error']


def test_create_custom_factor_validates_formula_first(app, monkeypatch):
    class FakeEngine:
        def validate_custom_factor_formula(self, formula):
            return {'valid': False, 'error': '不允许的函数: eval()'}

        def create_factor_definition(self, *args, **kwargs):
            raise AssertionError('不应该在公式校验失败时创建因子')

    monkeypatch.setattr(ai_tools, '_get_factor_engine', lambda: FakeEngine())
    outcome = execute_tool(
        'create_custom_factor',
        {'factor_id': 'f1', 'factor_name': 'F1', 'factor_formula': 'eval("1")'},
    )
    assert outcome['ok'] is False
    assert '白名单' in outcome['error']


def test_list_data_jobs_reports_token_state(app, monkeypatch):
    monkeypatch.delenv('TUSHARE_TOKEN', raising=False)
    outcome = execute_tool('list_data_jobs', {})
    assert outcome['ok'] is True
    job_types = {job['job_type'] for job in outcome['result']['jobs']}
    assert 'wide_table_builder' in job_types
    assert 'daily_basic' in job_types
    daily = next(j for j in outcome['result']['jobs'] if j['job_type'] == 'daily_basic')
    assert daily['needs_tushare_token'] is True
    assert outcome['result']['tushare_token_configured'] is False
