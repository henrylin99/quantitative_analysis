"""行情与数据源 API（数据来自扶摇快照，降级见 market_snapshot_service）。"""

from flask import Blueprint, jsonify, request
from loguru import logger

from app.services.market_snapshot_service import get_market_snapshot_service

market_bp = Blueprint("market_api", __name__, url_prefix="/api/market")
datasources_bp = Blueprint("datasources_api", __name__, url_prefix="/api/datasources")


def _ok(data) -> "tuple":
    return jsonify({"code": 200, "message": "成功", "data": data})


def _error(message: str, status: int = 500) -> "tuple":
    return jsonify({"code": status, "message": message, "data": None}), status


def _parse_codes(raw: str, limit: int = 200) -> list:
    codes = [code.strip() for code in (raw or "").split(",") if code.strip()]
    return codes[:limit]


@market_bp.route("/snapshot", methods=["GET"])
def get_snapshot():
    """按代码取实时快照（逗号分隔，≤200 只）。"""
    codes = _parse_codes(request.args.get("codes", ""))
    if not codes:
        return _error("缺少 codes 参数（逗号分隔的 ts_code，≤200 只）", 400)
    try:
        quotes = get_market_snapshot_service().get_quotes(codes)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"行情快照API错误: {exc}")
        return _error(f"行情快照获取失败: {exc}")
    return _ok({"quotes": quotes, "updated_at": None})


@market_bp.route("/dashboard", methods=["GET"])
def get_dashboard():
    """市场看板聚合（实时；扶摇异常时降级本地最近交易日）。"""
    try:
        return _ok(get_market_snapshot_service().get_dashboard())
    except Exception as exc:  # noqa: BLE001
        logger.error(f"市场看板API错误: {exc}")
        return _error(f"市场看板获取失败: {exc}")


@market_bp.route("/indices", methods=["GET"])
def get_indices():
    """指数实时快照（可选 codes 参数，默认看板四指数）。"""
    codes = _parse_codes(request.args.get("codes", "")) or None
    try:
        return _ok({"indices": get_market_snapshot_service().get_indices(codes)})
    except Exception as exc:  # noqa: BLE001
        logger.error(f"指数行情API错误: {exc}")
        return _error(f"指数行情获取失败: {exc}")


@market_bp.route("/dragon-tiger", methods=["GET"])
def get_dragon_tiger():
    """龙虎榜（board: all/org/hot_money；date 格式 YYYYMMDD，可空=最近发布日）。"""
    board = request.args.get("board", "all")
    if board not in ("all", "org", "hot_money"):
        return _error("board 取值须为 all/org/hot_money", 400)
    date = (request.args.get("date") or "").strip() or None
    try:
        return _ok(get_market_snapshot_service().get_dragon_tiger(board_type=board, date=date))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"龙虎榜API错误: {exc}")
        return _error(f"龙虎榜获取失败: {exc}")


@market_bp.route("/auction-benchmark", methods=["GET"])
def get_auction_benchmark():
    """盘前竞价短线风向标（date 可空=当日；支持一年内历史）。"""
    date = (request.args.get("date") or "").strip() or None
    try:
        return _ok(get_market_snapshot_service().get_auction_benchmark(date=date))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"竞价风向标API错误: {exc}")
        return _error(f"竞价风向标获取失败: {exc}")


@datasources_bp.route("/status", methods=["GET"])
def get_datasource_status():
    """三数据源健康状态（探测结果缓存 5 分钟；?force=1 强制重探）。"""
    force = (request.args.get("force") or "").lower() in ("1", "true", "yes")
    try:
        return _ok(get_market_snapshot_service().get_source_status(force=force))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"数据源状态API错误: {exc}")
        return _error(f"数据源状态获取失败: {exc}")
