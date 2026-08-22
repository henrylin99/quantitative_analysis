"""只读 SQL 校验与执行卡点的回归测试。

覆盖 2026-08 修复的安全问题:
- LLM/模板/规则生成的 SQL 只允许单条只读 SELECT
- 执行在隔离的只读 SQLite 查询库上进行（与应用主库物理隔离）
"""
import os
import tempfile

import pandas as pd
import pytest
from flask import Flask

from app.services.sql_generator import validate_readonly_sql
from app.services.text2sql_engine import QueryExecutor


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM stock_business LIMIT 10",
        "select ts_code, daily_close from stock_business where daily_close > 100;",
        "WITH t AS (SELECT ts_code FROM stock_business) SELECT * FROM t",
        "SELECT REPLACE(stock_name, 'x', 'y') FROM stock_business",  # REPLACE 是合法函数
        "SELECT /* 块注释 */ 1",
    ],
)
def test_readonly_selects_pass(sql):
    ok, error = validate_readonly_sql(sql)
    assert ok, f"{sql} 应通过校验: {error}"


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE query_history",
        "SELECT 1; DROP TABLE x",                      # 多语句
        "WITH t AS (SELECT 1) INSERT INTO t SELECT 2",  # CTE 写入变体
        "ATTACH DATABASE '/tmp/x.db' AS x",
        "-- select 1\nDROP TABLE x",                    # 注释藏关键字
        "PRAGMA table_info(x)",
        "UPDATE stock_business SET close = 0",
        "REPLACE INTO stock_business VALUES (1)",
        "DELETE FROM query_history",
        "",
    ],
)
def test_write_statements_rejected(sql):
    ok, _ = validate_readonly_sql(sql)
    assert not ok, f"{sql!r} 应被拒绝"


def test_executor_runs_select_on_isolated_readonly_db():
    """SELECT 走隔离查询库；写语句在卡点被拒，应用主库不可触达。"""
    with tempfile.TemporaryDirectory() as td:
        pd.DataFrame(
            {"ts_code": ["000001.SZ", "000002.SZ"], "close": [10.5, 20.3], "trade_date": ["20260101"] * 2}
        ).to_parquet(os.path.join(td, "stock_business.parquet"))

        app = Flask(__name__)
        app.config["DATA_DIR"] = td
        executor = QueryExecutor()

        with app.app_context():
            result = executor.execute(
                "SELECT ts_code, daily_close FROM stock_business WHERE daily_close > 15"
            )
            assert result["success"]
            assert result["row_count"] == 1
            assert result["data"][0]["ts_code"] == "000002.SZ"

            rejected = executor.execute("DROP TABLE stock_business")
            assert not rejected["success"]
            assert "只读" in rejected["error"]

        # 查询库文件落在 DATA_DIR 下，而不是应用主库
        assert os.path.exists(os.path.join(td, "text2sql_query.db"))


def test_executor_rejects_multi_statement_exfiltration():
    with tempfile.TemporaryDirectory() as td:
        app = Flask(__name__)
        app.config["DATA_DIR"] = td
        executor = QueryExecutor()
        with app.app_context():
            result = executor.execute("SELECT 1; SELECT 2")
            assert not result["success"]
