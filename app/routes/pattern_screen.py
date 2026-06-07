"""形态选股页面路由。"""
from flask import Blueprint, render_template

pattern_screen_bp = Blueprint('pattern_screen', __name__)


@pattern_screen_bp.route('/pattern-screen/')
def index():
    """形态选股页面。"""
    return render_template('pattern_screen.html')
