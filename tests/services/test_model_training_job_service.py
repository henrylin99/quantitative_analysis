from app.services.model_training_job_service import ModelTrainingJobService


def test_training_job_service_uses_resolved_training_dates():
    class FakeManager:
        def resolve_training_date_range(self, model_id, start_date, end_date):
            return {
                "model_id": model_id,
                "start_date": "2024-06-01",
                "end_date": "2024-06-10",
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "adjusted": True,
                "message": "训练结束日期已自动回退到可计算未来收益的最近日期: 2024-06-10",
            }

        def train_model(self, model_id, start_date, end_date, progress_callback=None):
            if progress_callback:
                progress_callback(100.0, "训练完成", f"实际训练区间: {start_date} 至 {end_date}")
            return {"success": True, "metrics": {"sample_count": 1}, "model_path": "models/demo.pkl"}

    service = ModelTrainingJobService(manager=FakeManager(), job_store={})

    job = service.submit_job("demo", "2024-06-01", "2024-06-11")

    assert job["start_date"] == "2024-06-01"
    assert job["end_date"] == "2024-06-10"
    assert job["requested_end_date"] == "2024-06-11"
    assert job["date_range_adjusted"] is True
    assert any("自动回退" in log for log in job["logs"])
