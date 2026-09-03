"""trial API 合约：统一 {code, message, data} 信封；意外异常一律 500，参数缺失 400。"""
import pytest

pytestmark = pytest.mark.module_trial


@pytest.fixture()
def client(app):
    return app.test_client()


def test_market_brief_returns_envelope(client, monkeypatch):
    import app.api.trial_api as trial_api

    monkeypatch.setattr(trial_api, "market_brief_payload", lambda: {"date": "2026-09-01"})

    response = client.get("/api/trial/market-brief")

    assert response.status_code == 200
    assert response.get_json() == {"code": 200, "message": "成功", "data": {"date": "2026-09-01"}}


def test_moneyflow_unexpected_error_is_500(client, monkeypatch):
    import app.api.trial_api as trial_api

    def boom():
        raise RuntimeError("parquet 缺失")

    monkeypatch.setattr(trial_api, "moneyflow_payload", boom)

    response = client.get("/api/trial/moneyflow")

    assert response.status_code == 500
    body = response.get_json()
    assert body["code"] == 500
    assert body["data"] is None


def test_stock_radar_unexpected_error_is_500_not_400(client, monkeypatch):
    import app.api.trial_api as trial_api

    def boom(_codes):
        raise RuntimeError("数据源不可用")

    monkeypatch.setattr(trial_api, "stock_radar_payload", boom)

    response = client.get("/api/trial/stock-radar?ts_codes=000001.SZ")

    assert response.status_code == 500
    assert response.get_json()["code"] == 500


def test_stock_radar_normalizes_and_dedupes_ts_codes(client, monkeypatch):
    import app.api.trial_api as trial_api

    captured = {}

    def fake_payload(ts_codes):
        captured["ts_codes"] = ts_codes
        return []

    monkeypatch.setattr(trial_api, "stock_radar_payload", fake_payload)

    response = client.get("/api/trial/stock-radar?ts_codes=sz.000001,%20SH.600000,sz.000001,")

    assert response.status_code == 200
    assert captured["ts_codes"] == ["SZ.000001", "SH.600000"]


def test_stock_panorama_requires_ts_code(client, monkeypatch):
    response = client.get("/api/trial/stock-panorama")

    assert response.status_code == 400
    assert "ts_code" in response.get_json()["message"]


def test_stock_panorama_unexpected_error_is_500(client, monkeypatch):
    import app.api.trial_api as trial_api

    def boom(_code):
        raise RuntimeError("坏了")

    monkeypatch.setattr(trial_api, "stock_panorama_payload", boom)

    response = client.get("/api/trial/stock-panorama?ts_code=000001.SZ")

    assert response.status_code == 500


def test_heatmap_envelope_carries_trade_date(client, monkeypatch):
    import app.api.trial_api as trial_api

    class FakeHeatmapService:
        def get_heatmap_data(self):
            return [{"trade_date": "2026-09-01", "name": "银行"}], [{"ts_code": "000001.SZ"}]

    monkeypatch.setattr(trial_api, "HeatmapService", FakeHeatmapService)

    response = client.get("/api/trial/heatmap")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["trade_date"] == "2026-09-01"
    assert data["sectors"][0]["name"] == "银行"
