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


@main_bp.route('/data-management')
def data_management():
    """数据管理页面"""
    return render_template('data_management/index.html')

@main_bp.route('/test-simple-chart')
def test_simple_chart():
    """简单图表测试页面"""
    with open('test_simple_chart.html', 'r', encoding='utf-8') as f:
        return f.read()

@main_bp.route('/api-test')
def api_test():
    """API测试页面"""
    return render_template('api_test.html')





 
