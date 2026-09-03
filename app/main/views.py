from flask import current_app, render_template, request
from app.main import main_bp
from app.services.trial_analytics import (
    financial_health_payload,
    market_brief_payload,
    moneyflow_payload,
    stock_panorama_payload,
    stock_radar_payload,
)
from startup_runtime import build_health_report, inspect_parquet_data_assets

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


@main_bp.route('/ai-workbench')
def ai_workbench():
    """AI 智能工作台页面"""
    return render_template('ai_workbench.html')


@main_bp.route('/trial/market-brief')
def market_brief():
    """每日市场简报生成器"""
    try:
        payload = market_brief_payload()
    except Exception as exc:
        return render_template(
            'market_brief.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'advance_count': 0,
                'decline_count': 0,
                'flat_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0,
                'turnover_total': 0.0,
            },
            brief_lines=[],
            brief_text='',
            top_amount=[],
            industry_top=[],
            industry_bottom=[],
            top_mf=[],
            special_stats={
                'first_limit_count': 0,
                'multi_limit_count': 0,
                'bullish_engulfing_count': 0,
                'consec_up_2p_count': 0,
                'consec_up_3p_count': 0,
                'consec_up_5p_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0,
            },
            error=str(exc),
        )

    return render_template('market_brief.html', **payload)


@main_bp.route('/trial/financial-health')
def financial_health():
    """财务健康度评分卡"""
    try:
        payload = financial_health_payload()
    except Exception as exc:
        return render_template(
            'financial_health.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'avg_score': 0.0,
                'max_score': 0,
                'min_score': 0,
                'full_score_count': 0,
                'qualified_count': 0,
            },
            score_distribution=[{'score': i, 'count': 0, 'label': f'{i} 分'} for i in range(6)],
            scored_rows=[],
            min_equity_threshold=1e7,
            error=str(exc),
        )

    return render_template('financial_health.html', **payload)


@main_bp.route('/trial/stock-radar', methods=['GET'])
def stock_radar():
    """个股对比雷达图"""
    raw_codes = request.args.get('ts_codes', '').strip()
    ts_codes = [code.strip().upper() for code in raw_codes.split(',') if code.strip()]

    # 保持输入顺序并去重
    seen = set()
    ts_codes = [code for code in ts_codes if not (code in seen or seen.add(code))]

    try:
        payload = stock_radar_payload(ts_codes)
    except Exception as exc:
        return render_template(
            'stock_radar.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'input_codes': [],
            },
            radar_axes=[
                {'name': '估值', 'max': 1},
                {'name': '成长', 'max': 1},
                {'name': '技术', 'max': 1},
                {'name': '资金', 'max': 1},
            ],
            radar_series=[],
            stock_rows=[],
            input_codes_text=raw_codes,
            error=str(exc),
        )

    return render_template('stock_radar.html', **payload)


@main_bp.route('/trial/stock-panorama', methods=['GET'])
def stock_panorama():
    """个股全景展示"""
    ts_code = request.args.get('ts_code', '').strip().upper()

    try:
        payload = stock_panorama_payload(ts_code)
    except Exception as exc:
        return render_template(
            'stock_panorama.html',
            overview=None,
            financial_panel=[],
            technical_panel=[],
            moneyflow_panel=[],
            status_panel=[],
            detail_rows=[],
            special_flags={},
            radar_chart={'labels': ['估值', '成长', '技术', '资金'], 'values': [0, 0, 0, 0]},
            input_code=request.args.get('ts_code', ''),
            latest_trade_date='',
            error=str(exc),
        )

    return render_template(
        'stock_panorama.html',
        input_code=ts_code,
        **payload,
    )


@main_bp.route('/trial/moneyflow')
def moneyflow_stats():
    """主力资金流入流出统计页面"""
    try:
        payload = moneyflow_payload()
    except Exception as exc:
        return render_template(
            'moneyflow_stats.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'industry_count': 0,
                'total_net_mf_amount': 0.0,
                'positive_stock_count': 0,
                'negative_stock_count': 0,
            },
            top_inflow=[],
            bottom_outflow=[],
            industry_rows=[],
            error=str(exc),
        )

    return render_template('moneyflow_stats.html', **payload)


def inspect_data_management_status():
    connected, existing_tables, non_empty_tables = inspect_parquet_data_assets()

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


@main_bp.route('/trial/feature-intro')
def feature_intro():
    """功能介绍：用通俗语言介绍大宽表的数据结构"""
    return render_template('feature_intro.html')

 
