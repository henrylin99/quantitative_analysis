"""板块热力图页面路由。"""
from flask import Blueprint, render_template
from loguru import logger
from app.services.heatmap_service import HeatmapService

heatmap_routes = Blueprint('heatmap_routes', __name__, url_prefix='/heatmap')


@heatmap_routes.route('/')
def index():
    """板块热力图页面。"""
    try:
        service = HeatmapService()
        sectors, stocks = service.get_heatmap_data()
        trade_date = sectors[0]['trade_date'] if sectors else ''
        return render_template(
            'heatmap.html',
            sectors_json=sectors,
            stocks_json=stocks,
            trade_date=trade_date,
        )
    except Exception as e:
        logger.error(f"热力图加载失败: {e}")
        return render_template(
            'heatmap.html',
            sectors_json=[],
            stocks_json=[],
            trade_date='',
            error='数据加载失败，请确认 data/data.parquet 是否存在',
        )
