from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.data_jobs.service import DataJobService

pytestmark = pytest.mark.module_data_jobs


class _DedupStore:
    def find_active_duplicate(self, job_type, params):
        assert job_type == "stock_basic"
        assert params == {"start_date": "20260101"}
        return SimpleNamespace(id=88)

    def create_run(self, job_type, params):
        return SimpleNamespace(id=101, status="pending", job_type=job_type, params_json=params)

    def update_run_status(self, run, status, progress=None, error_message=None):
        run.status = status
        return run


def test_submit_same_job_and_params_is_rejected():
    service = DataJobService(state_store=_DedupStore())

    with patch("app.services.data_jobs.service.run_data_job.delay") as delay:
        with pytest.raises(ValueError, match="duplicate running job"):
            service.submit("stock_basic", {"start_date": "20260101"})

    delay.assert_not_called()
