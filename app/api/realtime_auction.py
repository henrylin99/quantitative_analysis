"""实时分析-集合竞价与异动监控 API（数据来自扶摇集合竞价/特色数据域）。

短线风向标竞价基准与个股异动原因复用 /api/market 既有路由
（auction-benchmark / anomaly-analysis），本蓝图只承载新接入的
集合竞价快照、竞价机会筛选、可选日期与异动股票监控名单。
"""

from flask import Blueprint, jsonify, request
from loguru import logger

from app.services.board_market_service import get_board_market_service
from app.utils.request_parsing import parse_int_arg

realtime_auction_bp = Blueprint(
    "realtime_auction_api", __name__, url_prefix="/api/realtime-analysis/auction"
)


def _ok(data) -> "tuple":
    return jsonify({"code": 200, "message": "成功", "data": data})


def _error(message: str, status: int = 500) -> "tuple":
    return jsonify({"code": status, "message": message, "data": None}), status


def _parse_list(raw: str, limit: int) -> list:
    items = [item.strip() for item in (raw or "").split(",") if item.strip()]
    return items[:limit]


@realtime_auction_bp.route("/snapshot", methods=["GET"])
def get_auction_snapshot():
    """集合竞价快照（codes 逗号分隔 ≤100 只；stage=live/final 可空）。"""
    codes = _parse_list(request.args.get("codes", ""), 100)
    if not codes:
        return _error("缺少 codes 参数（逗号分隔的 ts_code，≤100 只）", 400)
    # 文档写 finallive，实测上游合法值为 live/final
    stage = (request.args.get("stage") or "").strip() or None
    try:
        return _ok(get_board_market_service().get_auction_snapshot(codes, stage=stage))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"集合竞价快照API错误: {exc}")
        return _error(f"集合竞价快照获取失败: {exc}")


@realtime_auction_bp.route("/opportunities", methods=["GET"])
def get_auction_opportunities():
    """集合竞价个股机会筛选（date YYYYMMDD 可空=当日实时；size 1~20）。"""
    params = {
        "date": (request.args.get("date") or "").strip() or None,
        "warn_types": _parse_list(request.args.get("warn_types", ""), 20) or None,
        "market": (request.args.get("market") or "").strip() or None,
        "exclude_st": (request.args.get("exclude_st") or "").strip().lower()
        in ("1", "true", "yes"),
        "sort_by": (request.args.get("sort_by") or "").strip() or None,
        "sort_order": (request.args.get("sort_order") or "").strip() or None,
    }
    try:
        params["page"] = parse_int_arg("page", 1, min_val=1)
        params["size"] = parse_int_arg("size", 20, min_val=1, max_val=20)
        return _ok(get_board_market_service().get_auction_opportunities(**params))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"竞价机会API错误: {exc}")
        return _error(f"竞价机会获取失败: {exc}")


@realtime_auction_bp.route("/opportunity-dates", methods=["GET"])
def get_auction_opportunity_dates():
    """集合竞价可选交易日期（YYYYMMDD 升序 + latest_date）。"""
    try:
        return _ok(get_board_market_service().get_auction_opportunity_dates())
    except Exception as exc:  # noqa: BLE001
        logger.error(f"竞价日期API错误: {exc}")
        return _error(f"竞价可选日期获取失败: {exc}")


@realtime_auction_bp.route("/abnormal", methods=["GET"])
def get_abnormal_monitor():
    """异动股票监控名单（state=current/history；size ≤30）。"""
    state = (request.args.get("state") or "").strip() or "current"
    try:
        page = parse_int_arg("page", 1, min_val=1)
        size = parse_int_arg("size", 30, min_val=1, max_val=30)
        return _ok(get_board_market_service().get_abnormal_monitor(state=state, page=page, size=size))
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"异动股票API错误: {exc}")
        return _error(f"异动股票获取失败: {exc}")
