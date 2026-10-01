"""僵尸数据任务清理：启动时只清超过超时时间的 run，多进程部署不误杀在跑任务。"""
from datetime import timedelta

import pytest

from app.services.data_jobs.parquet_state_store import ParquetDataJobStateStore

pytestmark = pytest.mark.module_data_jobs


@pytest.fixture()
def store(tmp_path):
    return ParquetDataJobStateStore(base_dir=str(tmp_path / 'data_job_state'))


def _create_run(store, job_type='stock_basic', params=None):
    run = store.create_run(job_type, params or {})
    return store.update_run_status(run, 'running', progress=10.0)


def _backdate(store, run, seconds):
    """把 run 的 started_at 回拨，模拟它已经跑了很久。"""
    from app.utils.time_utils import now_local

    df = store.store.read_frame(store.TABLE_RUNS)
    old = (now_local() - timedelta(seconds=seconds)).isoformat()
    df.loc[df['id'] == run.id, 'started_at'] = old
    with store.store.locked(store.TABLE_RUNS):
        store.store.write_frame(store.TABLE_RUNS, df)


def test_stale_run_gets_reaped(store):
    run = _create_run(store)
    _backdate(store, run, seconds=7200)  # 超过默认 1 小时超时

    reaped = store.reap_stale_runs()
    assert [r.id for r in reaped] == [run.id]
    assert store.get_run(run.id).status == 'failed'


def test_recent_run_survives_startup_reap(store):
    """多 worker 场景：另一个进程刚提交、正在执行的任务不能被误杀。"""
    run = _create_run(store)  # started_at = 刚刚

    reaped = store.reap_stale_runs()
    assert reaped == []
    assert store.get_run(run.id).status == 'running'


def test_finished_runs_never_touched(store):
    run = _create_run(store)
    _backdate(store, run, seconds=7200)
    store.update_run_status(store.get_run(run.id), 'success')

    assert store.reap_stale_runs() == []
    assert store.get_run(run.id).status == 'success'
