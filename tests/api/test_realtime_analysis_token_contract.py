import importlib
from unittest.mock import patch

import app.services.realtime_data_manager as realtime_data_manager_module


def test_realtime_analysis_passes_tushare_token_from_environment(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "demo-token")
    calls = []

    def fake_init(self, tushare_token=None):
        calls.append(tushare_token)
        self.tushare_token = tushare_token
        self.pro = None
        self.minute_sync_service = None

    with patch.object(realtime_data_manager_module.RealtimeDataManager, "__init__", fake_init):
        module = importlib.import_module("app.api.realtime_analysis")
        importlib.reload(module)

    assert calls
    assert calls[-1] == "demo-token"
