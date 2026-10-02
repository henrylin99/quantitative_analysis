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


def test_query_fund_registered_as_read_tool():
    tool = next(t for t in ai_tools.AI_TOOLS if t.name == 'query_fund')
    assert tool.kind == 'read'
    spec = tool.to_spec()
    topics = spec['function']['parameters']['properties']['topic']['enum']
    assert 'performance' in topics and 'holdings' in topics


def test_query_fund_dispatches_by_topic(app, monkeypatch):
    calls = {}

    class FakeService:
        def get_performance(self, thscode):
            calls['hit'] = ('performance', thscode)
            return {'thscode': thscode}

    monkeypatch.setattr('app.services.fund_service.get_fund_service', lambda: FakeService())

    outcome = execute_tool('query_fund', {'thscode': '510300.SH', 'topic': 'performance'})
    assert outcome['ok'] is True
    assert calls['hit'] == ('performance', '510300.SH')


def test_query_fund_validates_input(app):
    missing = execute_tool('query_fund', {})
    assert missing['ok'] is False
    assert 'thscode' in missing['error']

    bad_topic = execute_tool('query_fund', {'thscode': '510300.SH', 'topic': 'nope'})
    assert bad_topic['ok'] is False
    assert 'topic' in bad_topic['error']


def test_query_fund_maps_fuyao_error(app, monkeypatch):
    from app.utils.data_sources.fuyao_client import FuyaoError

    class FakeService:
        def get_profile(self, thscode):
            raise FuyaoError('3004', '该基金类型不支持')

    monkeypatch.setattr('app.services.fund_service.get_fund_service', lambda: FakeService())
    outcome = execute_tool('query_fund', {'thscode': '025480.OF'})
    assert outcome['ok'] is False
    assert '3004' in outcome['error']


# ---------------- 因子区间批量计算（calculate_factors_range） ----------------

def test_calculate_factors_range_submits_factor_compute_job(app, monkeypatch):
    captured = {}

    def fake_submit(job_type, params):
        captured['job_type'] = job_type
        captured['params'] = params
        return SimpleNamespace(
            id=11, job_type=job_type, status='queued', progress=0.0,
            progress_message='已入队', error_message=None,
        )

    fake_engine = SimpleNamespace(
        get_factor_list=lambda: [{'factor_id': 'alpha_001'}, {'factor_id': 'ma_cross'}]
    )
    monkeypatch.setattr(ai_tools, '_get_data_job_service', lambda: SimpleNamespace(submit=fake_submit))
    monkeypatch.setattr(ai_tools, '_get_factor_engine', lambda: fake_engine)

    outcome = execute_tool(
        'calculate_factors_range',
        {'start_date': '20260101', 'end_date': '2026-09-30',
         'factor_ids': ['alpha_001'], 'ts_codes': ['000001.SZ']},
    )
    assert outcome['ok'] is True
    assert outcome['result']['run_id'] == 11
    assert captured['job_type'] == 'factor_compute'
    # 日期归一化为 YYYY-MM-DD；列表参数以逗号串透传（ScriptRunner 按逗号拆分）
    assert captured['params']['start_date'] == '2026-01-01'
    assert captured['params']['end_date'] == '2026-09-30'
    assert captured['params']['factor_ids'] == 'alpha_001'
    assert captured['params']['ts_codes'] == '000001.SZ'


def test_calculate_factors_range_validates_dates_and_factors(app, monkeypatch):
    fake_engine = SimpleNamespace(
        get_factor_list=lambda: [{'factor_id': 'alpha_001'}]
    )
    monkeypatch.setattr(ai_tools, '_get_factor_engine', lambda: fake_engine)

    bad_order = execute_tool(
        'calculate_factors_range', {'start_date': '20260930', 'end_date': '20260101'}
    )
    assert bad_order['ok'] is False
    assert '不能晚于' in bad_order['error']

    bad_date = execute_tool(
        'calculate_factors_range', {'start_date': '2026/01/01', 'end_date': '20260930'}
    )
    assert bad_date['ok'] is False
    assert '日期格式' in bad_date['error']

    unknown = execute_tool(
        'calculate_factors_range',
        {'start_date': '20260101', 'end_date': '20260930', 'factor_ids': ['nope_001']},
    )
    assert unknown['ok'] is False
    assert 'list_factors' in unknown['error']


def test_calculate_factors_range_defaults_to_all_factors(app, monkeypatch):
    captured = {}

    def fake_submit(job_type, params):
        captured['params'] = params
        return SimpleNamespace(id=12, job_type=job_type, status='queued',
                               progress=0.0, progress_message='', error_message=None)

    monkeypatch.setattr(ai_tools, '_get_data_job_service', lambda: SimpleNamespace(submit=fake_submit))
    monkeypatch.setattr(ai_tools, '_get_factor_engine', lambda: SimpleNamespace(get_factor_list=lambda: []))

    outcome = execute_tool(
        'calculate_factors_range', {'start_date': '20260101', 'end_date': '20260131'}
    )
    assert outcome['ok'] is True
    assert 'factor_ids' not in captured['params']


# ---------------- 回测（run_backtest / get_backtest_status） ----------------

class FakeBacktestRepo:
    """替换 BacktestRepository：类级共享状态，工具实例化前后都可编程。"""

    created = []
    summaries = {}
    results = {}

    def __init__(self, store=None):
        pass

    @classmethod
    def reset(cls):
        cls.created = []
        cls.summaries = {}
        cls.results = {}

    def create_run(self, strategy_config, start_date, end_date,
                   initial_capital, rebalance_frequency):
        FakeBacktestRepo.created.append({
            'strategy_config': strategy_config,
            'start_date': start_date,
            'end_date': end_date,
            'initial_capital': initial_capital,
            'rebalance_frequency': rebalance_frequency,
        })
        return {'id': 42}

    @classmethod
    def update_summary(cls, run_id, summary):
        cls.summaries.setdefault(run_id, {}).update(summary)

    @classmethod
    def get_run(cls, run_id):
        # 与真实仓储一致：不存在的 run 返回 None
        if run_id not in cls.summaries:
            return None
        return {
            'id': run_id,
            'summary': dict(cls.summaries.get(run_id, {})),
            'start_date': '2026-01-01',
            'end_date': '2026-09-30',
        }

    @classmethod
    def get_result(cls, run_id):
        return cls.results.get(run_id)


def _patch_backtest_stack(monkeypatch, repo_cls=FakeBacktestRepo):
    repo_cls.reset()
    FakeBacktestRepo.results[42] = {
        'initial_capital': 1000000.0,
        'final_value': 1120000.0,
        'total_return': 0.12,
        'strategy_config': {'benchmark_index': '399300.SZ'},
        'performance_metrics': {
            'annualized_return': 0.15, 'sharpe_ratio': 1.2,
            'max_drawdown': -0.08, 'win_rate': 0.55,
        },
        'failed_signal_dates': ['2026-02-02'],
    }
    monkeypatch.setattr('app.services.parquet_state_store.BacktestRepository', repo_cls)
    monkeypatch.setattr('app.services.parquet_state_store.ParquetStateStore', lambda: None)
    monkeypatch.setattr('app.tasks.backtest_tasks.reap_orphans_once', lambda: [])
    monkeypatch.setattr('app.tasks.backtest_tasks.mark_run_active', lambda run_id: None)
    started = []
    monkeypatch.setattr(
        'app.tasks.backtest_tasks.run_backtest_task',
        lambda *args, **kwargs: started.append(args),
    )
    return started


def test_run_backtest_submits_async_run(app, monkeypatch):
    started = _patch_backtest_stack(monkeypatch)

    outcome = execute_tool(
        'run_backtest',
        {'factor_ids': ['alpha_001'], 'start_date': '20260101',
         'end_date': '20260930', 'benchmark_index': '399300.SZ', 'top_n': 10},
    )
    assert outcome['ok'] is True
    assert outcome['result']['run_id'] == 42
    assert outcome['result']['status'] == 'queued'

    created = FakeBacktestRepo.created[0]
    assert created['strategy_config'] == {
        'selection_method': 'factor_based',
        'factor_list': ['alpha_001'],
        'top_n': 10,
        'benchmark_index': '399300.SZ',
    }
    assert created['rebalance_frequency'] == 'monthly'
    assert FakeBacktestRepo.summaries[42] == {'status': 'queued'}
    # 后台线程拿到的参数与提交一致
    assert started[0][0] == 42
    assert started[0][1]['factor_list'] == ['alpha_001']


def test_run_backtest_validates_params(app, monkeypatch):
    _patch_backtest_stack(monkeypatch)

    missing = execute_tool(
        'run_backtest', {'start_date': '20260101', 'end_date': '20260930'}
    )
    assert missing['ok'] is False
    assert 'factor_ids' in missing['error']

    bad_freq = execute_tool(
        'run_backtest',
        {'factor_ids': ['alpha_001'], 'start_date': '20260101',
         'end_date': '20260930', 'rebalance_frequency': 'yearly'},
    )
    assert bad_freq['ok'] is False
    assert 'rebalance_frequency' in bad_freq['error']

    bad_topn = execute_tool(
        'run_backtest',
        {'factor_ids': ['alpha_001'], 'start_date': '20260101',
         'end_date': '20260930', 'top_n': 0},
    )
    assert bad_topn['ok'] is False
    assert 'top_n' in bad_topn['error']


def test_get_backtest_status_returns_metrics_when_succeeded(app, monkeypatch):
    _patch_backtest_stack(monkeypatch)
    monkeypatch.setattr(ai_tools.time, 'sleep', lambda s: None)

    FakeBacktestRepo.update_summary(42, {'status': 'succeeded'})

    outcome = execute_tool('get_backtest_status', {'run_id': 42})
    assert outcome['ok'] is True
    metrics = outcome['result']['metrics']
    assert outcome['result']['status'] == 'succeeded'
    assert metrics['total_return'] == 0.12
    assert metrics['annualized_return'] == 0.15
    assert metrics['max_drawdown'] == -0.08
    assert metrics['benchmark_index'] == '399300.SZ'
    assert outcome['result']['failed_signal_dates_count'] == 1


def test_get_backtest_status_waits_until_finished(app, monkeypatch):
    _patch_backtest_stack(monkeypatch)
    monkeypatch.setattr(ai_tools.time, 'sleep', lambda s: None)

    FakeBacktestRepo.update_summary(42, {'status': 'queued'})
    # 第一次查询仍 queued，第二次起标记完成：wait 轮询应取到最终状态
    original_get_run = FakeBacktestRepo.get_run
    calls = {'n': 0}

    def flip_after_first(self, run_id):
        calls['n'] += 1
        if calls['n'] > 1:
            FakeBacktestRepo.update_summary(run_id, {'status': 'succeeded'})
        return original_get_run(run_id)

    monkeypatch.setattr(FakeBacktestRepo, 'get_run', flip_after_first)

    outcome = execute_tool('get_backtest_status', {'run_id': 42, 'wait_seconds': 30})
    assert outcome['ok'] is True
    assert outcome['result']['status'] == 'succeeded'
    assert calls['n'] >= 2


def test_get_backtest_status_running_reports_note(app, monkeypatch):
    _patch_backtest_stack(monkeypatch)
    monkeypatch.setattr(ai_tools.time, 'sleep', lambda s: None)

    FakeBacktestRepo.update_summary(42, {'status': 'running'})

    outcome = execute_tool('get_backtest_status', {'run_id': 42, 'wait_seconds': 0})
    assert outcome['ok'] is True
    assert outcome['result']['status'] == 'running'
    assert 'wait_seconds' in outcome['result']['note']

    missing = execute_tool('get_backtest_status', {'run_id': 999})
    assert missing['ok'] is False
    assert '未找到回测记录' in missing['error']
