from flask import Blueprint, render_template, request, redirect, url_for, flash
from loguru import logger

# 创建蓝图
ml_factor_routes = Blueprint('ml_factor_routes', __name__, url_prefix='/ml-factor')

@ml_factor_routes.route('/')
def index():
    """多因子选股系统主页 - 因子管理"""
    return render_template('ml_factor/index.html')

@ml_factor_routes.route('/dashboard')
def dashboard():
    """仪表盘页面"""
    return render_template('ml_factor/dashboard.html')

@ml_factor_routes.route('/factors')
def factors():
    """因子管理页面"""
    return render_template('ml_factor/index.html')

@ml_factor_routes.route('/models')
def models():
    """模型管理页面"""
    return render_template('ml_factor/models.html')

@ml_factor_routes.route('/scoring')
def scoring():
    """股票评分页面"""
    return render_template('ml_factor/scoring.html')

@ml_factor_routes.route('/portfolio')
def portfolio():
    """投资组合页面"""
    return render_template('ml_factor/portfolio.html')

@ml_factor_routes.route('/analysis')
def analysis():
    """分析报告页面"""
    return render_template('ml_factor/analysis.html')

@ml_factor_routes.route('/backtest')
def backtest():
    """回测验证页面"""
    return render_template('ml_factor/backtest.html') 