import logging

from flask import Blueprint, jsonify, request

from app.services.data_jobs.registry import JobRegistry
from app.services.data_jobs.service import DataJobService
from app.services.wide_table_status import get_wide_table_status
from app.utils.request_parsing import parse_int_arg


data_jobs_bp = Blueprint("data_jobs", __name__, url_prefix="/api/data-jobs")

logger = logging.getLogger(__name__)

_service = None
_registry = None


def get_data_job_service() -> DataJobService:
    global _service
    if _service is None:
        _service = DataJobService()
    return _service


def get_job_registry() -> JobRegistry:
    global _registry
    if _registry is None:
        _registry = JobRegistry()
    return _registry


@data_jobs_bp.route("/submit", methods=["POST"])
def submit_job():
    payload = request.get_json(silent=True) or {}
    job_type = payload.get("job_type")
    if not job_type:
        return jsonify({"success": False, "error": "missing job_type"}), 400

    # 服务端 allowlist：只允许页面可见任务经 API 提交，
    # 防止绕过前端直接触发隐藏任务/危险任务
    registry = get_job_registry()
    try:
        registry.get_job(job_type)
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if not registry.is_visible(job_type):
        return jsonify({
            "success": False,
            "error": f"任务 {job_type} 未开放 API 提交（仅限数据管理页面/内部使用）",
        }), 403

    # 大宽表构建任务需通过 18:00 校验
    if job_type == "wide_table_builder":
        from flask import current_app
        status = get_wide_table_status(current_app.config.get("DATA_DIR"))
        if not status["past_cutoff"]:
            return jsonify({
                "success": False,
                "error": "当前时间未过 18:00，数据源可能尚未下载完毕，请稍后再试",
            }), 400

    params = payload.get("params", {})
    try:
        run = get_data_job_service().submit(job_type, params)
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        logger.exception("提交数据任务 %s 失败", job_type)
        return jsonify({"success": False, "error": "服务器内部错误，请查看服务日志"}), 500

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
    include_hidden = (request.args.get("include_hidden") or "").lower() in {"1", "true", "yes"}
    jobs = [
        j.__dict__
        for j in get_data_job_service().list_job_definitions(visible_only=not include_hidden)
    ]
    return jsonify({"success": True, "jobs": jobs, "count": len(jobs)})


@data_jobs_bp.route("/list", methods=["GET"])
def list_runs():
    try:
        limit = parse_int_arg("limit", 50, min_val=1, max_val=500)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    status = request.args.get("status")
    runs = [run.to_dict() for run in get_data_job_service().list_runs(limit=limit, status=status)]
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
    except Exception:
        logger.exception("重试数据任务 %s 失败", run_id)
        return jsonify({"success": False, "error": "服务器内部错误，请查看服务日志"}), 500

    return jsonify({"success": True, "run_id": run.id, "status": run.status})


@data_jobs_bp.route("/init-status", methods=["GET"])
def init_status():
    """数据资产初始化状态（Parquet 健康检查 + 推荐下一步），供新前端数据管理页使用。"""
    from app.main.views import inspect_data_management_status

    try:
        return jsonify({"success": True, "status": inspect_data_management_status()})
    except Exception:
        logger.exception("读取数据资产初始化状态失败")
        return jsonify({"success": False, "error": "服务器内部错误，请查看服务日志"}), 500


@data_jobs_bp.route("/wide-table/status", methods=["GET"])
def wide_table_status():
    """返回大宽表状态：是否存在、日期、是否需要更新、是否过了 18:00。"""
    try:
        from flask import current_app
        data_dir = current_app.config.get("DATA_DIR")
        status = get_wide_table_status(data_dir)
        return jsonify({"success": True, "status": status})
    except Exception:
        logger.exception("读取大宽表状态失败")
        return jsonify({"success": False, "error": "服务器内部错误，请查看服务日志"}), 500


@data_jobs_bp.route("/wide-table/build", methods=["POST"])
def build_wide_table():
    """提交大宽表构建任务。需通过 18:00 校验。"""
    try:
        # 后端强制 18:00 校验，防止绕过 UI 直接调 API
        from flask import current_app
        status = get_wide_table_status(current_app.config.get("DATA_DIR"))
        if not status["past_cutoff"]:
            return jsonify({
                "success": False,
                "error": "当前时间未过 18:00，数据源可能尚未下载完毕，请稍后再试",
            }), 400

        run = get_data_job_service().submit("wide_table_builder", {})
        # 构建成功后清缓存（inline 模式立即生效，celery 模式在 task 完成后清）
        if run.status == "success":
            from app.services.data_reader import ParquetDataReader
            ParquetDataReader.invalidate_stock_business_cache()
            from app.services.text2sql_engine import get_text2sql_engine
            get_text2sql_engine().query_executor.invalidate_cache()
        return jsonify({
            "success": True,
            "run_id": run.id,
            "job_type": run.job_type,
            "status": run.status,
        })
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        logger.exception("提交大宽表构建任务失败")
        return jsonify({"success": False, "error": "服务器内部错误，请查看服务日志"}), 500
