"""指数目录检索端点 + get_ma_data（stk_factor 股票分区口径）契约测试。"""

import pandas as pd
import pytest
from flask import Flask

from app.api.market_api import market_bp
from app.services.data_reader import ParquetDataReader

pytestmark = pytest.mark.module_data_jobs


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = Flask(__name__)
    app.config.update(TESTING=True, DATA_DIR=str(tmp_path))
    app.register_blueprint(market_bp)
    return app


def _write_index_basic(tmp_path):
    df = pd.DataFrame(
        [
            {"ts_code": "000300.SH", "name": "沪深300", "fullname": "沪深300指数",
             "market": "CSI", "publisher": "中证", "category": "规模指数",
             "base_date": "20050408", "list_date": "20050408"},
            {"ts_code": "881101.SI", "name": "半导体", "fullname": "申万半导体行业指数",
             "market": "SW", "publisher": "申万", "category": "行业指数",
             "base_date": "20040102", "list_date": "20140221"},
            {"ts_code": "105653.MI", "name": "MSCI俄罗斯", "fullname": "MSCI俄罗斯指数",
             "market": "MSCI", "publisher": "MSCI指数", "category": "规模指数",
             "base_date": "19941230", "list_date": "19961201"},
        ]
    )
    df.to_parquet(tmp_path / "index_basic.parquet", index=False)


def test_index_search_matches_name_and_code(app, tmp_path):
    _write_index_basic(tmp_path)
    client = app.test_client()

    resp = client.get("/api/market/indices/search?q=沪深")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["indices"][0]["ts_code"] == "000300.SH"

    resp = client.get("/api/market/indices/search?q=881101")
    assert resp.get_json()["data"]["total"] == 1
def test_index_search_defaults_to_domestic(app, tmp_path):
    _write_index_basic(tmp_path)
    client = app.test_client()

    resp = client.get("/api/market/indices/search")
    ts_codes = [item["ts_code"] for item in resp.get_json()["data"]["indices"]]
    # 无关键词时不倒出海外指数
    assert "105653.MI" not in ts_codes
    assert "000300.SH" in ts_codes


def test_index_search_missing_file_returns_empty(app, tmp_path):
    client = app.test_client()
    resp = client.get("/api/market/indices/search?q=沪深")
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"indices": [], "total": 0}


def test_get_ma_data_reads_stk_factor_stock_partition(tmp_path):
    stock_dir = tmp_path / "stk_factor" / "stock" / "ts_code=000001.SZ"
    stock_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": ["2026-09-29", "2026-09-30"],
            "ma_qfq_5": [10.0, 10.5],
            "ema_qfq_5": [9.9, 10.1],
        }
    ).to_parquet(stock_dir / "data.parquet", index=False)

    reader = ParquetDataReader(data_dir=str(tmp_path))
    series = reader.get_ma_data("000001.SZ")

    assert series is not None
    assert series["ts_code"] == "000001.SZ"
    # 取最新一行，键名保持 ma5/ema5 风格
    assert series["ma5"] == 10.5
    assert series["ema5"] == 10.1
    assert "ma120" not in series.index  # 只暴露实际存在的周期

    assert reader.get_ma_data("999999.SZ") is None
