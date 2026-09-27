"""基金数据 API（数据来自扶摇 /api/fund/*，见 fund_service）。"""

import re

from flask import Blueprint, jsonify, request
from loguru import logger

from app.services.fund_service import get_fund_service
from app.utils.data_sources.fuyao_client import FuyaoError

fund_bp = Blueprint("fund_api", __name__, url_prefix="/api/fund")

_THSCODE_RE = re.compile(r"^\d{6}\.(OF|SH|SZ)$")


def _ok(data) -> "tuple":
    return jsonify({"code": 200, "message": "成功", "data": data})


def _error(message: str, status: int = 500) -> "tuple":
    return jsonify({"code": status, "message": message, "data": None}), status


def _require_thscode() -> "tuple | None":
    """校验 thscode 参数（6 位代码 + 市场/场外后缀），非法返回错误响应。"""
    thscode = (request.args.get("thscode") or "").strip()
    if not thscode:
        return _error("缺少 thscode 参数（如 510300.SH、025480.OF）", 400)
    if not _THSCODE_RE.match(thscode):
        return _error(f"thscode 格式非法: {thscode}（须为 6 位代码 + .OF/.SH/.SZ 后缀）", 400)
    return None


def _fund_call(handler):
    """统一执行服务调用并兜错：3001/3004/1002/5003 转 404（标的/维度无数据），其余转 502。"""
    try:
        return _ok(handler())
    except FuyaoError as exc:
        logger.warning(f"[fund] 扶摇业务错误: {exc}")
        if str(exc.code) in ("3001", "3004", "1002", "5003"):
            return _error(f"基金数据不可用: {exc.message}（code={exc.code}）", 404)
        return _error(f"基金数据获取失败: {exc}", 502)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("基金API错误")
        return _error(f"基金数据获取失败: {exc}")


@fund_bp.route("/search", methods=["GET"])
def search_funds():
    """基金检索（名称/代码模糊匹配；asset_type: fund-etf/fund-lof/fund-otc，可空=全部基金）。"""
    query = (request.args.get("q") or "").strip()
    if not query:
        return _error("缺少 q 参数（基金名称或代码）", 400)
    asset_type = (request.args.get("asset_type") or "").strip() or None
    if asset_type and asset_type not in ("fund-etf", "fund-lof", "fund-otc"):
        return _error("asset_type 取值须为 fund-etf/fund-lof/fund-otc", 400)
    try:
        limit = min(50, max(1, int(request.args.get("limit", 20))))
    except ValueError:
        return _error("limit 须为整数", 400)
    return _fund_call(
        lambda: {
            "query": query,
            "items": get_fund_service().search_funds(query, asset_type=asset_type, limit=limit),
        }
    )


@fund_bp.route("/profile", methods=["GET"])
def get_profile():
    """基金基本资料（成立日期、管理人、经理、规模、单位净值等）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_profile(request.args["thscode"].strip()))


@fund_bp.route("/snapshot", methods=["GET"])
def get_snapshot():
    """场内基金实时快照（仅 ETF/LOF）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_snapshot(request.args["thscode"].strip()))


@fund_bp.route("/history", methods=["GET"])
def get_history():
    """ETF 前复权历史日线（start/end 格式 YYYYMMDD，窗口超 5 年自动截断）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    if not start or not end:
        return _error("缺少 start/end 参数（格式 YYYYMMDD）", 400)
    return _fund_call(
        lambda: get_fund_service().get_history(request.args["thscode"].strip(), start, end)
    )


@fund_bp.route("/performance", methods=["GET"])
def get_performance():
    """业绩聚合：最新净值 + 区间收益（同类排名）+ 各区间最大回撤。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_performance(request.args["thscode"].strip()))


@fund_bp.route("/nav", methods=["GET"])
def get_nav_series():
    """净值序列（range: week/month/tmonth/hyear/year/twoyear/tyear/fyear，默认 year）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    nav_range = (request.args.get("range") or "year").strip()
    if nav_range not in ("week", "month", "tmonth", "hyear", "year", "twoyear", "tyear", "fyear"):
        return _error("range 取值须为 week/month/tmonth/hyear/year/twoyear/tyear/fyear", 400)
    return _fund_call(
        lambda: get_fund_service().get_nav_series(request.args["thscode"].strip(), range=nav_range)
    )


@fund_bp.route("/holdings", methods=["GET"])
def get_holdings():
    """最新重仓持仓：汇总（股票/债券/基金占比、集中度）+ 明细列表。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_holdings(request.args["thscode"].strip()))


@fund_bp.route("/holders", methods=["GET"])
def get_holders():
    """持有人结构（机构/个人占比、户数）+ 前十大持有人。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_holders(request.args["thscode"].strip()))


@fund_bp.route("/asset-allocation", methods=["GET"])
def get_asset_allocation():
    """历史资产配置（报告期股票/债券/存款/其他占比）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(
        lambda: get_fund_service().get_asset_allocation(request.args["thscode"].strip())
    )


@fund_bp.route("/industry-allocation", methods=["GET"])
def get_industry_allocation():
    """历史行业配置（report_period 如 2026Q2）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(
        lambda: get_fund_service().get_industry_allocation(request.args["thscode"].strip())
    )


@fund_bp.route("/diagnostics", methods=["GET"])
def get_diagnostics():
    """基金诊断详情（诊断维度/同类对比/韧性指标）。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_diagnostics(request.args["thscode"].strip()))


@fund_bp.route("/dividends", methods=["GET"])
def get_dividends():
    """历史分红记录。"""
    invalid = _require_thscode()
    if invalid:
        return invalid
    return _fund_call(lambda: get_fund_service().get_dividends(request.args["thscode"].strip()))


@fund_bp.route("/manager", methods=["GET"])
def get_manager():
    """基金经理详情（manager_id 来自基金基本资料 manager_info）。"""
    manager_id = (request.args.get("manager_id") or "").strip()
    if not manager_id:
        return _error("缺少 manager_id 参数", 400)
    return _fund_call(lambda: get_fund_service().get_manager(manager_id))


@fund_bp.route("/company", methods=["GET"])
def get_company():
    """基金公司详情（company_id 来自基金基本资料）。"""
    company_id = (request.args.get("company_id") or "").strip()
    if not company_id:
        return _error("缺少 company_id 参数", 400)
    return _fund_call(lambda: get_fund_service().get_company(company_id))
