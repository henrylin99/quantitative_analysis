"""数据洞察 API：估值分位 / 资金流深历史 / 同业对比 / 组合相关性 / 日内统计 / 事件复盘。"""
from flask import Blueprint, jsonify, request
from loguru import logger

from app.services import insights_service as svc

insights_api = Blueprint('insights_api', __name__, url_prefix='/api/insights')


def _ok(data):
    return jsonify({'code': 200, 'message': '成功', 'data': data})


def _fail(e, status=500):
    logger.error(f"insights API 错误: {e}")
    return jsonify({'code': status, 'message': f'服务器错误: {e}', 'data': None}), status


@insights_api.route('/valuation', methods=['GET'])
def valuation():
    ts_code = request.args.get('ts_code', '').strip()
    if not ts_code:
        return _fail('缺少 ts_code', 400)
    try:
        return _ok(svc.valuation_history(ts_code))
    except Exception as e:
        return _fail(e)


@insights_api.route('/valuation/thermometer', methods=['GET'])
def thermometer():
    try:
        return _ok(svc.valuation_thermometer())
    except Exception as e:
        return _fail(e)


@insights_api.route('/moneyflow/streaks', methods=['GET'])
def mf_streaks():
    try:
        days = min(max(request.args.get('days', 20, type=int), 5), 60)
        min_streak = min(max(request.args.get('min_streak', 3, type=int), 2), 10)
        top = min(max(request.args.get('top', 20, type=int), 5), 50)
        return _ok(svc.moneyflow_streaks(days=days, min_streak=min_streak, top=top))
    except Exception as e:
        return _fail(e)


@insights_api.route('/moneyflow/divergence', methods=['GET'])
def mf_divergence():
    try:
        days = min(max(request.args.get('days', 20, type=int), 5), 60)
        top = min(max(request.args.get('top', 20, type=int), 5), 50)
        return _ok(svc.moneyflow_divergence(days=days, top=top))
    except Exception as e:
        return _fail(e)


@insights_api.route('/peer-compare', methods=['GET'])
def peer_compare():
    ts_code = request.args.get('ts_code', '').strip()
    if not ts_code:
        return _fail('缺少 ts_code', 400)
    try:
        top = min(max(request.args.get('top', 15, type=int), 5), 30)
        return _ok(svc.peer_compare(ts_code, top_peers=top))
    except Exception as e:
        return _fail(e)


@insights_api.route('/correlation', methods=['POST'])
def correlation():
    data = request.get_json(silent=True) or {}
    codes = data.get('ts_codes') or []
    if not isinstance(codes, list):
        return _fail('ts_codes 须为数组', 400)
    try:
        days = min(max(int(data.get('days') or 120), 30), 500)
        return _ok(svc.portfolio_correlation(codes, days=days))
    except Exception as e:
        return _fail(e)


@insights_api.route('/intraday', methods=['GET'])
def intraday():
    ts_code = request.args.get('ts_code', '').strip()
    if not ts_code:
        return _fail('缺少 ts_code', 400)
    try:
        days = min(max(request.args.get('days', 60, type=int), 10), 120)
        return _ok(svc.intraday_stats(ts_code, days=days))
    except Exception as e:
        return _fail(e)


@insights_api.route('/event-dates', methods=['GET'])
def event_dates():
    try:
        return _ok(svc.event_archive_dates())
    except Exception as e:
        return _fail(e)


@insights_api.route('/event-replay', methods=['GET'])
def event_replay():
    date = request.args.get('date', '').strip()
    try:
        return _ok(svc.event_replay(date))
    except Exception as e:
        return _fail(e)
