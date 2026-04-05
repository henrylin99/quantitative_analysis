from app import create_app
from app.celery_app import celery
from app.extensions import db
from app.services.data_jobs.registry import JobRegistry
from app.services.data_jobs.runner import ScriptRunner
from app.services.data_jobs.state_store import DataJobStateStore


def _build_app():
    return create_app("development")


def _build_registry():
    return JobRegistry()


def _build_state_store():
    return DataJobStateStore(db.session)


def _build_runner():
    return ScriptRunner()


@celery.task(name="data_jobs.run")
def run_data_job(run_id: int):
    """Background task entrypoint for data jobs."""

    app = _build_app()
    with app.app_context():
        store = _build_state_store()
        run = store.get_run(run_id)
        if run is None:
            return {"run_id": run_id, "status": "missing"}

        store.update_run_status(run, "running", progress=5.0, progress_message="任务开始执行")

        registry = _build_registry()
        definition = registry.get_job(run.job_type)
        runner = _build_runner()

        run.source_name = getattr(run, "source_name", None) or definition.source_name
        run.source_mode = getattr(run, "source_mode", None) or definition.source_mode
        store.save_run(run)

        runner_params = dict(run.params_json or {})
        runner_params.setdefault("source_name", run.source_name or definition.source_name)
        runner_params.setdefault("source_mode", run.source_mode or definition.source_mode)
        snapshot_tag = getattr(run, "snapshot_tag", None)
        if snapshot_tag:
            runner_params.setdefault("snapshot_tag", snapshot_tag)

        completed = runner.run_script(definition.script_path, params=runner_params)
        run.result_json = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:] if completed.stdout else "",
            "stderr": completed.stderr[-4000:] if completed.stderr else "",
        }

        if completed.returncode == 0:
            store.update_run_status(run, "success", progress=100.0, progress_message="任务执行完成")
            store.save_run(run)
            return {"run_id": run_id, "status": "success"}

        run.error_message = completed.stderr[-1000:] if completed.stderr else "task failed"
        store.update_run_status(
            run,
            "failed",
            progress=100.0,
            error_message=run.error_message,
            progress_message="任务执行失败",
        )
        store.save_run(run)
        return {"run_id": run_id, "status": "failed", "error": run.error_message}
