"""试用功能只读 JSON API — 与对应 Flask 页面共用 trial_analytics / heatmap_service 的计算结果。"""
from flask import jsonify, request
from loguru import logger

from app.api import api_bp
from app.services.heatmap_service import HeatmapService
from app.services.trial_analytics import (
    financial_health_payload,
    market_brief_payload,
    moneyflow_payload,
    stock_panorama_payload,
    stock_radar_payload,
)


def _parse_ts_codes(raw):
    codes = [code.strip().upper() for code in (raw or '').split(',') if code.strip()]
    seen = set()
    return [code for code in codes if not (code in seen or seen.add(code))]


def _ok(data):
    return jsonify({'code': 200, 'message': '成功', 'data': data})


def _error(label: str, exc: Exception, status: int = 500):
    logger.error(f"{label}API错误: {exc}")
    return jsonify({'code': status, 'message': str(exc), 'data': None}), status


@api_bp.route('/trial/market-brief', methods=['GET'])
def api_market_brief():
    try:
        return _ok(market_brief_payload())
    except Exception as e:
        return _error('每日市场简报', e)


@api_bp.route('/trial/financial-health', methods=['GET'])
def api_financial_health():
    try:
        return _ok(financial_health_payload())
    except Exception as e:
        return _error('财务健康度', e)


@api_bp.route('/trial/financial-anomalies', methods=['GET'])
def api_financial_anomalies():
    try:
        from app.services.financial_quality_service import FinancialQualityService

        return _ok(FinancialQualityService().anomaly_scan())
    except Exception as e:
        return _error('财务异动扫描', e)


@api_bp.route('/trial/daily-alerts', methods=['GET'])
def api_daily_alerts():
    """每日预警扫描记录（?refresh=1 立即扫描一次）。"""
    try:
        from app.services.daily_alert_service import DailyAlertService

        limit = request.args.get('limit', type=int) or 30
        if request.args.get('refresh') == '1':
            DailyAlertService().run_scan(force=False)
        return _ok({'records': DailyAlertService().list_records(limit=limit)})
    except Exception as e:
        return _error('每日预警记录', e)


@api_bp.route('/trial/industry-rotation', methods=['GET'])
def api_industry_rotation():
    """行业轮动评分：动量 + 主力资金 + 估值分位三维截面 z-score。"""
    try:
        from app.services.industry_rotation_service import IndustryRotationService

        months = request.args.get('months', type=int) or 12
        force = request.args.get('refresh') == '1'
        return _ok(IndustryRotationService().run(months=months, force_refresh=force))
    except Exception as e:
        return _error('行业轮动评分', e)


@api_bp.route('/trial/financial-anomaly-backtest', methods=['GET'])
def api_financial_anomaly_backtest():
    """财务异动名单按披露日的前向收益（异动组 vs 全市场等权）。"""
    try:
        from app.services.signal_backtest_service import AnomalyForwardService

        force = request.args.get('refresh') == '1'
        return _ok(AnomalyForwardService().run(force_refresh=force))
    except Exception as e:
        return _error('财务异动前向收益', e)


@api_bp.route('/trial/moneyflow', methods=['GET'])
def api_moneyflow():
    try:
        return _ok(moneyflow_payload())
    except Exception as e:
        return _error('资金流统计', e)


@api_bp.route('/trial/stock-radar', methods=['GET'])
def api_stock_radar():
    try:
        ts_codes = _parse_ts_codes(request.args.get('ts_codes', ''))
        return _ok(stock_radar_payload(ts_codes))
    except Exception as e:
        return _error('个股对比雷达', e)


@api_bp.route('/trial/stock-panorama', methods=['GET'])
def api_stock_panorama():
    try:
        ts_code = request.args.get('ts_code', '').strip().upper()
        if not ts_code:
            return jsonify({'code': 400, 'message': '请提供股票代码 ts_code', 'data': None}), 400
        return _ok(stock_panorama_payload(ts_code))
    except Exception as e:
        return _error('个股全景', e)


@api_bp.route('/trial/heatmap', methods=['GET'])
def api_heatmap():
    try:
        sectors, stocks = HeatmapService().get_heatmap_data()
        return _ok({
            'sectors': sectors,
            'stocks': stocks,
            'trade_date': sectors[0]['trade_date'] if sectors else '',
        })
    except Exception as e:
        return _error('板块热力图', e)
