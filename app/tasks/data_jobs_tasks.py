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

        store.update_run_status(run, "running", progress=5.0)

        registry = _build_registry()
        definition = registry.get_job(run.job_type)
        runner = _build_runner()

        completed = runner.run_script(definition.script_path)
        run.result_json = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:] if completed.stdout else "",
            "stderr": completed.stderr[-4000:] if completed.stderr else "",
        }

        if completed.returncode == 0:
            store.update_run_status(run, "success", progress=100.0)
            store.save_run(run)
            return {"run_id": run_id, "status": "success"}

        run.error_message = completed.stderr[-1000:] if completed.stderr else "task failed"
        store.update_run_status(run, "failed", progress=100.0, error_message=run.error_message)
        store.save_run(run)
        return {"run_id": run_id, "status": "failed", "error": run.error_message}
