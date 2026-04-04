from flask import current_app, render_template, request
from sqlalchemy import inspect

from app.extensions import db
from app.main import main_bp
from app.services.stock_service import StockService
from startup_runtime import build_health_report

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


def inspect_data_management_status():
    existing_tables = set()
    non_empty_tables = set()
    connected = False

    try:
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        connected = True
        for table in existing_tables & {"stock_basic", "stock_trade_calendar", "data_job_run"}:
            count = db.session.execute(db.text(f"SELECT COUNT(*) FROM {table}")).scalar()
            if count and int(count) > 0:
                non_empty_tables.add(table)
    except Exception:
        connected = False

    return build_health_report(
        current_app.config,
        connected=connected,
        existing_tables=existing_tables,
        non_empty_tables=non_empty_tables,
    )


@main_bp.route('/data-management')
def data_management():
    """数据管理页面"""
    return render_template(
        'data_management/index.html',
        initialization_status=inspect_data_management_status(),
    )

@main_bp.route('/test-simple-chart')
def test_simple_chart():
    """简单图表测试页面"""
    with open('test_simple_chart.html', 'r', encoding='utf-8') as f:
        return f.read()

@main_bp.route('/api-test')
def api_test():
    """API测试页面"""
    return render_template('api_test.html')





 
