"""Paper trading 模拟盘 API（纯虚拟记账，无券商接口）。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.paper_trading_service import (
    DEFAULT_INITIAL_CASH,
    DEFAULT_TOP_N,
    PaperTradingService,
)

paper_trading_bp = Blueprint("paper_trading", __name__)


def _service() -> PaperTradingService:
    return PaperTradingService()


def _ok(data):
    return jsonify({"code": 200, "message": "成功", "data": data})


def _err(message: str, status: int = 400):
    return jsonify({"code": status, "message": message, "data": None}), status


@paper_trading_bp.route("/status", methods=["GET"])
def status():
    return _ok(_service().status())


@paper_trading_bp.route("/history", methods=["GET"])
def history():
    limit = request.args.get("limit", default=200, type=int)
    return _ok(_service().history(limit=max(1, min(limit, 1000))))


@paper_trading_bp.route("/alignment", methods=["GET"])
def alignment():
    return _ok(_service().alignment_report())


@paper_trading_bp.route("/run", methods=["POST"])
def run_daily():
    """手动触发一轮（结算→盯市→生成挂单）。"""
    return _ok(_service().run_daily())


@paper_trading_bp.route("/reset", methods=["POST"])
def reset():
    body = request.get_json(silent=True) or {}
    try:
        cash = float(body.get("initial_cash", DEFAULT_INITIAL_CASH))
        top_n = int(body.get("top_n", DEFAULT_TOP_N))
    except (TypeError, ValueError):
        return _err("参数非法")
    if cash <= 0 or not (1 <= top_n <= 50):
        return _err("initial_cash 需>0，top_n 需在 1~50")
    return _ok(_service().reset(initial_cash=cash, top_n=top_n))
