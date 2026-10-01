"""错误脱敏合约：500 响应不携带内部异常细节，完整堆栈只进日志。"""
from unittest.mock import patch

from flask import Flask

from app.api.text2sql_api import text2sql_bp


def test_text2sql_query_masks_500_details():
    app = Flask(__name__)
    app.register_blueprint(text2sql_bp)
    client = app.test_client()

    with patch(
        'app.api.text2sql_api.get_text2sql_engine',
        side_effect=RuntimeError('leak: /Users/x/stock_cursor.sqlite3 table schema'),
    ):
        resp = client.post('/api/text2sql/query', json={'query': '涨停的股票'})

    assert resp.status_code == 500
    error = resp.get_json()['error']
    assert 'leak' not in error
    assert 'stock_cursor' not in error
    assert '服务器内部错误' in error


def test_text2sql_suggestions_masks_500_details():
    app = Flask(__name__)
    app.register_blueprint(text2sql_bp)
    client = app.test_client()

    with patch(
        'app.api.text2sql_api.get_text2sql_engine',
        side_effect=RuntimeError('leak: internal engine state'),
    ):
        resp = client.get('/api/text2sql/suggestions')

    assert resp.status_code == 500
    assert 'leak' not in resp.get_json()['error']
