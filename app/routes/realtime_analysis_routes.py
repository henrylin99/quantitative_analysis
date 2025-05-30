"""
实时交易分析页面路由
提供实时分析系统的页面访问路由
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from loguru import logger

# 创建蓝图
realtime_analysis_routes = Blueprint('realtime_analysis_routes', __name__, url_prefix='/realtime-analysis')

@realtime_analysis_routes.route('/')
def index():
    """实时交易分析系统主页 - 数据管理"""
    return render_template('realtime_analysis/index.html')

@realtime_analysis_routes.route('/data')
def data():
    """数据管理页面"""
    return render_template('realtime_analysis/index.html')

@realtime_analysis_routes.route('/indicators')
def indicators():
    """技术指标分析页面"""
    return render_template('realtime_analysis/indicators.html')

@realtime_analysis_routes.route('/signals')
def signals():
    """交易信号管理页面"""
    return render_template('realtime_analysis/signals.html')

@realtime_analysis_routes.route('/monitor')
def monitor():
    """实时监控面板页面"""
    return render_template('realtime_analysis/monitor.html')

@realtime_analysis_routes.route('/risk')
def risk():
    """风险管理页面"""
    return render_template('realtime_analysis/risk_management.html')

@realtime_analysis_routes.route('/reports')
def reports():
    """分析报告中心页面"""
    return render_template('realtime_analysis/report_management.html')

@realtime_analysis_routes.route('/websocket')
def websocket():
    """WebSocket管理页面"""
    return render_template('realtime_analysis/websocket_management.html') 