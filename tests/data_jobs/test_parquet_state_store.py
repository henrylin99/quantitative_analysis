from pathlib import Path

import pytest
from app.services.parquet_state_store import ParquetStateStore

from app.services.data_jobs.parquet_state_store import ParquetDataJobStateStore

pytestmark = pytest.mark.module_data_jobs


def test_parquet_store_creates_and_reads_run(tmp_path):
    store = ParquetDataJobStateStore(base_dir=str(tmp_path / "state"))

    run = store.create_run(
        "daily_basic",
        {"start_date": "2026-06-04"},
        source_name="tushare",
        source_mode="incremental",
        snapshot_tag="2026-06-05",
        progress_message="已创建任务，等待调度",
    )

    assert run.id == 1
    assert run.status == "pending"
    assert run.source_name == "tushare"
    assert Path(tmp_path / "state" / "data_job_runs.parquet").is_file()

    fetched = store.get_run(1)
    assert fetched is not None
    assert fetched.job_type == "daily_basic"
    assert fetched.params_json == {"start_date": "2026-06-04"}


def test_parquet_store_detects_active_duplicate_and_filters_list(tmp_path):
    store = ParquetDataJobStateStore(base_dir=str(tmp_path / "state"))
    run = store.create_run("stock_basic", {"start_date": "20260101"})
    store.update_run_status(run, "queued", progress=0.0, progress_message="任务已入队")

    duplicate = store.find_active_duplicate("stock_basic", {"start_date": "20260101"})
    assert duplicate is not None
    assert duplicate.id == run.id

    store.update_run_status(run, "success", progress=100.0, progress_message="任务执行完成")
    assert store.find_active_duplicate("stock_basic", {"start_date": "20260101"}) is None

    failed = store.create_run("moneyflow", {"start_date": "20260102"})
    store.update_run_status(failed, "failed", progress=100.0, error_message="boom", progress_message="任务执行失败")

    failed_runs = store.list_runs(limit=10, status="failed")
    assert len(failed_runs) == 1
    assert failed_runs[0].job_type == "moneyflow"


def test_parquet_store_defaults_to_dedicated_data_job_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    store = ParquetDataJobStateStore()
    run = store.create_run("stock_basic", {})

    assert run.id == 1
    assert (tmp_path / "data_job_state" / "data_job_runs.parquet").is_file()


def test_parquet_store_migrates_previous_ml_factor_state_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    previous_store = ParquetStateStore(base_dir=str(tmp_path / "ml_factor_state"))
    previous_store.write_frame(
        "data_job_runs",
        __import__("pandas").DataFrame(
            [
                {
                    "id": 7,
                    "job_type": "daily_basic",
                    "status": "success",
                    "progress": 100.0,
                    "progress_message": "任务执行完成",
                    "params_json": {"start_date": "2026-06-04"},
                    "source_name": "tushare",
                    "source_mode": "incremental",
                    "snapshot_tag": "2026-06-05",
                    "result_json": {"returncode": 0},
                    "error_message": None,
                    "log_text": None,
                    "queued_at": "2026-06-05T00:00:00",
                    "started_at": "2026-06-05T00:00:01",
                    "finished_at": "2026-06-05T00:00:02",
                    "created_at": "2026-06-05T00:00:00",
                    "updated_at": "2026-06-05T00:00:02",
                }
            ]
        ),
    )

    store = ParquetDataJobStateStore()
    fetched = store.get_run(7)

    assert fetched is not None
    assert fetched.job_type == "daily_basic"
    assert (tmp_path / "data_job_state" / "data_job_runs.parquet").is_file()
    assert not (tmp_path / "ml_factor_state" / "data_job_runs.parquet").exists()
