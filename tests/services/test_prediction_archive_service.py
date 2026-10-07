"""预测跟踪归档测试：压缩摘要、同日去重、持久化。"""

from __future__ import annotations

import pytest

from app.services.prediction_archive_service import PredictionArchiveService


def _fake_report():
    return {
        "model_ids": ["m1", "m2", "m3"],
        "start_date": "2026-09-01",
        "end_date": "2026-10-05",
        "models": {
            "m1": {
                "ic_series": [],
                "top_n_series": [],
                "ic_by_horizon": {
                    "1": {"ic_mean": 0.03, "ic_ir": 0.4, "n_dates": 20},
                    "5": {"ic_mean": 0.05, "ic_ir": 0.6, "n_dates": 20},
                },
                "summary": {"base_horizon": 5, "n_dates": 20,
                            "spread_mean": 0.01, "top_excess_mean": 0.004},
            },
            "m2": {
                "ic_series": [],
                "top_n_series": [],
                "ic_by_horizon": {"5": {"ic_mean": -0.02, "n_dates": 20}},
                "summary": {"base_horizon": 5, "n_dates": 20,
                            "spread_mean": -0.005, "top_excess_mean": -0.001},
            },
            "m3": {"error": "区间内无预测"},
        },
        "model_consistency": {"series": [{"date": "2026-10-05", "mean_corr": 0.42},
                                         {"date": "2026-10-04", "mean_corr": 0.38}]},
    }


@pytest.fixture()
def _patched_track(monkeypatch):
    calls = []

    class _FakeSvc:
        def track(self, **kwargs):
            calls.append(kwargs)
            return _fake_report()

    import app.services.prediction_tracking as pt_mod
    monkeypatch.setattr(pt_mod, "PredictionTrackingService", _FakeSvc)
    return calls


class TestArchive:
    def test_archive_and_compact(self, tmp_path, _patched_track):
        svc = PredictionArchiveService(data_dir=str(tmp_path))
        record = svc.archive_today()
        assert "error" not in record
        assert record["n_models"] == 3
        m1 = record["models"]["m1"]
        assert m1["ic_mean_5d"] == 0.05
        assert m1["base_horizon"] == 5
        assert record["models"]["m3"] == {"error": "区间内无预测"}
        assert record["consistency_mean"] == pytest.approx(0.40)
        # ic_pool_mean = (0.05 + -0.02) / 2
        assert record["ic_pool_mean"] == pytest.approx(0.015)
        assert record["pred_end"] == "2026-10-05"

    def test_same_day_dedupe(self, tmp_path, _patched_track):
        svc = PredictionArchiveService(data_dir=str(tmp_path))
        svc.archive_today()
        calls = _patched_track
        assert len(calls) == 1
        again = svc.archive_today()
        assert len(calls) == 1  # 未重跑
        assert "error" not in again

    def test_force_reruns(self, tmp_path, _patched_track):
        svc = PredictionArchiveService(data_dir=str(tmp_path))
        svc.archive_today()
        svc.archive_today(force=True)
        assert len(_patched_track) == 2

    def test_track_error_recorded_not_persisted(self, tmp_path, monkeypatch):
        class _FakeSvc:
            def track(self, **kwargs):
                return {"error": "暂无预测数据"}

        import app.services.prediction_tracking as pt_mod
        monkeypatch.setattr(pt_mod, "PredictionTrackingService", _FakeSvc)
        svc = PredictionArchiveService(data_dir=str(tmp_path))
        record = svc.archive_today()
        assert record.get("error") == "暂无预测数据"
        assert svc.list_history() == []  # 错误不落归档

    def test_history_persisted_across_instances(self, tmp_path, _patched_track):
        PredictionArchiveService(data_dir=str(tmp_path)).archive_today()
        other = PredictionArchiveService(data_dir=str(tmp_path))
        assert len(other.list_history()) == 1
