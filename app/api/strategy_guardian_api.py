"""策略守护 API：登记/查询/删除/复活/手动复验/历史。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.strategy_guardian_service import StrategyGuardianService

strategy_guardian_bp = Blueprint("strategy_guardian", __name__)


def _ok(data):
    return jsonify({"code": 200, "message": "成功", "data": data})


def _err(message: str, status: int = 400):
    return jsonify({"code": status, "message": message, "data": None}), status


def _service() -> StrategyGuardianService:
    return StrategyGuardianService()


@strategy_guardian_bp.route("/strategies", methods=["GET"])
def list_strategies():
    return _ok(_service().list_strategies())


@strategy_guardian_bp.route("/strategies", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return _err("缺少必需参数: name")
    record = _service().register(
        name=name,
        kind=data.get("kind", "chip_signal"),
        params=data.get("params") or {},
        horizon=data.get("horizon", 10),
        months_eval=data.get("months_eval", 6),
        watch_excess=data.get("watch_excess", 0.0),
        retire_excess=data.get("retire_excess", -0.05),
        max_watch_days=data.get("max_watch_days", 10),
        signal=data.get("signal", "resonance"),
        top_n=data.get("top_n", 5),
        rebalance_days=data.get("rebalance_days", 20),
    )
    if "error" in record:
        return _err(record["error"])
    return _ok(record)


@strategy_guardian_bp.route("/strategies/<strategy_id>", methods=["DELETE"])
def remove(strategy_id):
    result = _service().remove(strategy_id)
    if "error" in result:
        return _err(result["error"], 404)
    return _ok(result)


@strategy_guardian_bp.route("/strategies/<strategy_id>/resume", methods=["POST"])
def resume(strategy_id):
    result = _service().resume(strategy_id)
    if "error" in result:
        return _err(result["error"], 404)
    return _ok(result)


@strategy_guardian_bp.route("/run", methods=["POST"])
def run():
    """手动复验（与 18:30 链同一入口，含推送）。重查询，分钟级。"""
    result = _service().run_daily(push=True)
    return _ok(result)


@strategy_guardian_bp.route("/history", methods=["GET"])
def history():
    strategy_id = request.args.get("strategy_id")
    limit = request.args.get("limit", default=200, type=int)
    return _ok(_service().history(strategy_id=strategy_id, limit=limit))
