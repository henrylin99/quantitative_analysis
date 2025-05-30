from flask import render_template, request
from app.main import main_bp
from app.services.stock_service import StockService

@main_bp.route('/')
def index():
    """首页"""
    return render_template('index.html')

@main_bp.route('/stocks')
def stocks():
    """股票列表页面"""
    return render_template('stocks.html')

@main_bp.route('/stock/<ts_code>')
def stock_detail(ts_code):
    """股票详情页面"""
    return render_template('stock_detail.html', ts_code=ts_code)

@main_bp.route('/analysis')
def analysis():
    """分析页面"""
    return render_template('analysis.html')

@main_bp.route('/screen')
def screen():
    """选股筛选页面"""
    return render_template('screen.html')

@main_bp.route('/backtest')
def backtest():
    """策略回测页面"""
    return render_template('backtest.html')

@main_bp.route('/realtime-analysis')
def realtime_analysis():
    """实时交易分析页面"""
    return render_template('realtime_analysis/index.html')

@main_bp.route('/realtime-analysis/indicators')
def realtime_indicators():
    """实时技术指标页面"""
    return render_template('realtime_analysis/indicators.html')

@main_bp.route('/realtime-analysis/signals')
def realtime_signals():
    """实时交易信号页面"""
    return render_template('realtime_analysis/signals.html')

@main_bp.route('/realtime-analysis/monitor')
def realtime_monitor():
    """实时监控面板页面"""
    return render_template('realtime_analysis/monitor.html')

@main_bp.route('/realtime-analysis/risk-management')
def realtime_risk_management():
    """实时风险管理页面"""
    return render_template('realtime_analysis/risk_management.html')

@main_bp.route('/realtime-analysis/report-management')
def realtime_report_management():
    """实时分析报告管理页面"""
    return render_template('realtime_analysis/report_management.html')

@main_bp.route('/realtime-analysis/websocket-management')
def websocket_management():
    """WebSocket推送管理页面"""
    return render_template('realtime_analysis/websocket_management.html')

@main_bp.route('/test-simple-chart')
def test_simple_chart():
    """简单图表测试页面"""
    with open('test_simple_chart.html', 'r', encoding='utf-8') as f:
        return f.read()





 