from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from app.services.ml_models import MLModelManager


class ModelTrainingJobService:
    """Lightweight in-process training job tracker for UI polling."""

    def __init__(self, manager: Optional[MLModelManager] = None, job_store: Optional[Dict[str, Dict[str, Any]]] = None):
        self.manager = manager or MLModelManager()
        self.job_store = job_store if job_store is not None else {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="model-train")

    def submit_job(self, model_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        job_id = str(uuid4())
        snapshot = {
            "job_id": job_id,
            "model_id": model_id,
            "start_date": start_date,
            "end_date": end_date,
            "status": "queued",
            "progress": 0.0,
            "step": "已加入训练队列",
            "logs": [f"已提交训练任务: {model_id}"],
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
            "started_at": None,
            "finished_at": None,
        }
        with self._lock:
            self.job_store[job_id] = snapshot
        self._executor.submit(self._run_job, job_id, model_id, start_date, end_date)
        return deepcopy(snapshot)

    def get_job_snapshot(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            snapshot = self.job_store.get(job_id)
            return deepcopy(snapshot) if snapshot is not None else None

    def _run_job(self, job_id: str, model_id: str, start_date: str, end_date: str) -> None:
        def progress_callback(progress: float, step: str, log_message: Optional[str] = None) -> None:
            with self._lock:
                snapshot = self.job_store[job_id]
                snapshot["status"] = "running"
                snapshot["progress"] = progress
                snapshot["step"] = step
                if snapshot["started_at"] is None:
                    snapshot["started_at"] = datetime.utcnow().isoformat()
                if log_message:
                    snapshot["logs"].append(log_message)

        try:
            progress_callback(5.0, "初始化训练任务", f"开始训练模型: {model_id}")
            result = self.manager.train_model(
                model_id,
                start_date,
                end_date,
                progress_callback=progress_callback,
            )

            with self._lock:
                snapshot = self.job_store[job_id]
                if result.get("success"):
                    snapshot["status"] = "success"
                    snapshot["progress"] = 100.0
                    snapshot["step"] = "训练完成"
                    snapshot["result"] = result
                    snapshot["logs"].append("模型训练完成")
                else:
                    snapshot["status"] = "failed"
                    snapshot["progress"] = 100.0
                    snapshot["step"] = "训练失败"
                    snapshot["error"] = result.get("error", "训练失败")
                    snapshot["logs"].append(f"训练失败: {snapshot['error']}")
                snapshot["finished_at"] = datetime.utcnow().isoformat()
        except Exception as exc:
            with self._lock:
                snapshot = self.job_store[job_id]
                snapshot["status"] = "failed"
                snapshot["progress"] = 100.0
                snapshot["step"] = "训练失败"
                snapshot["error"] = str(exc)
                snapshot["logs"].append(f"训练异常: {exc}")
                snapshot["finished_at"] = datetime.utcnow().isoformat()
