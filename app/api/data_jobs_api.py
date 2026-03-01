from flask import Blueprint, jsonify, request

from app.services.data_jobs.service import DataJobService


data_jobs_bp = Blueprint("data_jobs", __name__, url_prefix="/api/data-jobs")

_service = None


def get_data_job_service() -> DataJobService:
    global _service
    if _service is None:
        _service = DataJobService()
    return _service


@data_jobs_bp.route("/submit", methods=["POST"])
def submit_job():
    payload = request.get_json(silent=True) or {}
    job_type = payload.get("job_type")
    if not job_type:
        return jsonify({"success": False, "error": "missing job_type"}), 400

    params = payload.get("params", {})
    try:
        run = get_data_job_service().submit(job_type, params)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify(
        {
            "success": True,
            "run_id": run.id,
            "job_type": run.job_type,
            "status": run.status,
        }
    )


@data_jobs_bp.route("/jobs", methods=["GET"])
def list_jobs():
    jobs = [j.__dict__ for j in get_data_job_service().list_job_definitions()]
    return jsonify({"success": True, "jobs": jobs, "count": len(jobs)})


@data_jobs_bp.route("/list", methods=["GET"])
def list_runs():
    limit = int(request.args.get("limit", 50))
    runs = [run.to_dict() for run in get_data_job_service().list_runs(limit=limit)]
    return jsonify({"success": True, "runs": runs, "count": len(runs)})


@data_jobs_bp.route("/<int:run_id>", methods=["GET"])
def get_run(run_id: int):
    run = get_data_job_service().get_run(run_id)
    if run is None:
        return jsonify({"success": False, "error": "run not found"}), 404
    return jsonify({"success": True, "run": run.to_dict()})


@data_jobs_bp.route("/<int:run_id>/retry", methods=["POST"])
def retry_run(run_id: int):
    try:
        run = get_data_job_service().retry(run_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({"success": True, "run_id": run.id, "status": run.status})
