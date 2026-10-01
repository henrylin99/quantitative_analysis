"""Text2SQL 虚拟表日期范围加载：历史日期可查、无日期默认最新日、截断 fail-closed。

用 tmp 目录自造 Parquet，不依赖真实 data/ 数据。
"""
import pandas as pd
import pytest
from flask import Flask

from app.services.text2sql_engine import QueryExecutor


@pytest.fixture()
def executor(tmp_path):
    app = Flask(__name__)
    app.config['DATA_DIR'] = str(tmp_path)
    df = pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000001.SZ', '000002.SZ'],
        'trade_date': ['2026-01-01', '2026-01-01', '2026-01-02', '2026-01-02'],
        'close': [10.0, 20.0, 11.0, 21.0],
    })
    df.to_parquet(tmp_path / 'stock_business.parquet')
    with app.app_context():
        yield QueryExecutor()


def test_dated_query_loads_requested_date(executor):
    """历史日期查询必须命中该日期的数据，而不是静默返回最新交易日。"""
    result = executor.execute(
        "SELECT ts_code, daily_close FROM stock_business "
        "WHERE trade_date = '2026-01-01' AND daily_close > 15"
    )
    assert result['success'] is True
    assert result['row_count'] == 1
    assert result['data'][0]['ts_code'] == '000002.SZ'
    scope = result['data_scope']
    assert scope['key'] == '2026-01-01~2026-01-01'
    assert scope['tables']['stock_business']['loaded_end'] == '2026-01-01'


def test_dated_query_with_no_matching_rows_returns_empty(executor):
    """请求的日期不存在时返回空集 + 明确口径，而不是最新日的数据。"""
    result = executor.execute(
        "SELECT ts_code FROM stock_business WHERE trade_date = '2025-12-31'"
    )
    assert result['success'] is True
    assert result['row_count'] == 0
    assert result['data_scope']['key'] == '2025-12-31~2025-12-31'


def test_undated_query_defaults_to_latest_day(executor):
    result = executor.execute('SELECT COUNT(*) AS n FROM stock_business')
    assert result['success'] is True
    assert result['data'][0]['n'] == 2
    assert result['data_scope']['key'] == 'latest'


def test_trade_date_without_literal_covers_history(executor):
    result = executor.execute(
        'SELECT COUNT(*) AS n FROM stock_business WHERE daily_close > 0 ORDER BY trade_date'
    )
    assert result['success'] is True
    assert result['data'][0]['n'] == 4
    assert result['data_scope']['key'] == 'history'


def test_truncated_range_fails_closed(executor):
    """显式范围被行数上限截断时拒绝执行；缓存命中后同样拒绝。"""
    executor.MAX_LOAD_ROWS = 1
    sql = "SELECT ts_code FROM stock_business WHERE trade_date >= '2026-01-01'"

    first = executor.execute(sql)
    assert first['success'] is False
    assert '加载上限' in first['error']

    second = executor.execute(sql)
    assert second['success'] is False
    assert '加载上限' in second['error']


def test_truncation_does_not_affect_other_scopes(executor):
    """被截断的宽范围不影响之后的小范围/最新日查询。"""
    executor.MAX_LOAD_ROWS = 1
    wide = executor.execute(
        "SELECT ts_code FROM stock_business WHERE trade_date >= '2026-01-01'"
    )
    assert wide['success'] is False

    latest = executor.execute('SELECT COUNT(*) AS n FROM stock_business')
    assert latest['success'] is True
    assert latest['data'][0]['n'] == 2


def test_execute_masks_internal_errors(executor, monkeypatch):
    """未知异常不外泄细节（路径/表结构），只返回通用消息。"""
    def _boom():
        raise RuntimeError('secret internal state at /Users/x/stock_cursor.sqlite3')

    monkeypatch.setattr(executor, '_open_readonly_connection', _boom)
    result = executor.execute('SELECT 1')
    assert result['success'] is False
    assert 'secret' not in result['error']
    assert 'stock_cursor' not in result['error']
