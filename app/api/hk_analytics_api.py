"""港股量化分析 API（/api/hk-analytics/*）。

市场统计 / 个股风险 / 扫描器三组的数据端点（港股无宏观/行业 ETF/
季度财务辅助表，「基本面与事件」组不适用）。计算实现在
app/services/hk_analytics_{market,risk,screener}.py，
本文件只做参数解析与 JSON 包装。
"""
from __future__ import annotations

import math

from flask import Blueprint, jsonify, request

from app.services import hk_analytics_market as market
from app.services import hk_analytics_risk as risk
from app.services import hk_analytics_screener as screener
from app.services.hk_analytics_base import symbols as all_symbols

hk_analytics_api = Blueprint("hk_analytics_api", __name__, url_prefix="/api/hk-analytics")


def _ok(payload):
    # 与全站 API 惯例一致：{code, message, data} 信封（前端 client.ts 的 apiGet 按此解包）
    return jsonify({"code": 200, "message": "ok", "data": payload})


def _err(message: str, code: int = 400):
    return jsonify({"code": code, "message": message, "data": None}), code


def _num(name: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
    raw = request.args.get(name)
    try:
        v = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    if math.isnan(v):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    return int(_num(name, default, lo, hi))


@hk_analytics_api.route("/symbols", methods=["GET"])
def _symbols():
    return _ok({"symbols": all_symbols()})


# ---------------------------------------------------------------- 市场统计

@hk_analytics_api.route("/market/internals", methods=["GET"])
def market_internals():
    try:
        return _ok(market.internals())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/relstrength", methods=["GET"])
def market_relstrength():
    try:
        return _ok(market.relstrength(
            period=_int("period", 60, 5, 500), ma_trend=_int("ma_trend", 20, 5, 200),
        ))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/volregime", methods=["GET"])
def market_volregime():
    try:
        return _ok(market.volregime(window=_int("window", 20, 5, 120)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/volcone", methods=["GET"])
def market_volcone():
    try:
        return _ok(market.volcone())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/dispersion", methods=["GET"])
def market_dispersion():
    try:
        return _ok(market.dispersion(window=_int("window", 60, 10, 250)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/persistence", methods=["GET"])
def market_persistence():
    try:
        return _ok(market.persistence(request.args.get("symbol")))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/seasonality", methods=["GET"])
def market_seasonality():
    try:
        return _ok(market.seasonality(request.args.get("symbol")))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/market/overnight", methods=["GET"])
def market_overnight():
    try:
        return _ok(market.overnight(request.args.get("symbol")))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


# ---------------------------------------------------------------- 个股风险

@hk_analytics_api.route("/risk/tailrisk", methods=["GET"])
def risk_tailrisk():
    try:
        return _ok(risk.tailrisk(window=_int("window", 63, 20, 250)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/risk/drawdown", methods=["GET"])
def risk_drawdown():
    try:
        return _ok(risk.drawdown(request.args.get("symbol")))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/risk/beta", methods=["GET"])
def risk_beta():
    try:
        return _ok(risk.beta(
            symbol=request.args.get("symbol"), window=_int("window", 126, 20, 500),
        ))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/risk/pairs", methods=["GET"])
def risk_pairs():
    try:
        sym_a = request.args.get("symbol_a")
        sym_b = request.args.get("symbol_b")
        if sym_a and sym_b:
            return _ok(risk.pairs_detail(sym_a, sym_b))
        return _ok(risk.pairs_scan(top=_int("top", 12, 3, 50)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/risk/sharpe", methods=["GET"])
def risk_sharpe():
    try:
        return _ok(risk.risk_adj_ranking(window=_int("window", 126, 20, 500)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/risk/effbets", methods=["GET"])
def risk_effbets():
    try:
        return _ok(risk.effbets(window=_int("window", 60, 20, 252)))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@hk_analytics_api.route("/risk/liquidity", methods=["GET"])
def risk_liquidity():
    try:
        return _ok(risk.liquidity())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


# ---------------------------------------------------------------- 扫描器

@hk_analytics_api.route("/screener/base", methods=["GET"])
def screener_base():
    try:
        return _ok(screener.base())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)
