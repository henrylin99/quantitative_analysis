from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import threading

import pytest

from app.services.data_jobs.service import DataJobService

pytestmark = pytest.mark.module_data_jobs


class _InlineStore:
    def __init__(self):
        self.run = SimpleNamespace(id=201, status="pending", job_type="stock_basic", params_json={})

    def create_run(self, job_type, params):
        self.run.job_type = job_type
        self.run.params_json = params
        return self.run

    def update_run_status(self, run, status, progress=None, error_message=None):
        run.status = status
        if progress is not None:
            run.progress = progress
        return run

    def get_run(self, run_id):
        assert run_id == self.run.id
        return self.run


def test_submit_runs_inline_when_execution_mode_is_inline():
    store = _InlineStore()
    task = MagicMock()
    started = threading.Event()
    main_return_checked = threading.Event()

    def _run_inline(run_id):
        assert run_id == store.run.id
        # 等 main 断言完 "submit 立即返回 queued" 再改状态，
        # 否则共享的 run 对象可能在断言前就被线程改成 success
        main_return_checked.wait(timeout=5)
        store.run.status = "success"
        started.set()
        return {"run_id": run_id, "status": "success"}

    task.side_effect = _run_inline
    task.delay = MagicMock()

    service = DataJobService(state_store=store, execution_mode="inline")

    with patch("app.services.data_jobs.service.run_data_job", task):
        run = service.submit("stock_basic", {})

    # inline 任务在后台线程执行：submit 立即返回 queued，不阻塞请求
    assert run.status == "queued"
    main_return_checked.set()
    assert started.wait(timeout=5), "后台线程未在时限内执行任务"
    task.delay.assert_not_called()
    assert store.run.status == "success"
