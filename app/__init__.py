from flask import Flask
from flask_cors import CORS
from config import config
from app.extensions import db, socketio
from app.utils.logger import setup_logger

def create_app(config_name='default'):
    """应用工厂函数"""
    app = Flask(__name__)
    
    # 加载配置
    app.config.from_object(config[config_name])
    
    # 初始化扩展
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='eventlet')
    CORS(app)
    
    # 设置日志
    setup_logger(app.config['LOG_LEVEL'], app.config['LOG_FILE'])
    
    # 注册蓝图
    from app.api import api_bp
    from app.api.ml_factor_api import ml_factor_bp
    from app.api.text2sql_api import text2sql_bp
    from app.api.realtime_analysis import realtime_analysis_bp
    from app.api.realtime_indicators import realtime_indicators_bp
    from app.api.realtime_signals import realtime_signals_bp
    from app.api.realtime_monitor import realtime_monitor_bp
    from app.api.realtime_risk import realtime_risk_bp
    from app.api.realtime_report import realtime_report_bp
    from app.api.websocket_api import websocket_api_bp
    from app.routes.ml_factor_routes import ml_factor_routes
    from app.routes.realtime_analysis_routes import realtime_analysis_routes
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(ml_factor_bp)
    app.register_blueprint(text2sql_bp)
    app.register_blueprint(realtime_analysis_bp)
    app.register_blueprint(realtime_indicators_bp, url_prefix='/api/realtime-analysis/indicators')
    app.register_blueprint(realtime_signals_bp, url_prefix='/api/realtime-analysis/signals')
    app.register_blueprint(realtime_monitor_bp, url_prefix='/api/realtime-analysis/monitor')
    app.register_blueprint(realtime_risk_bp, url_prefix='/api/realtime-analysis/risk')
    app.register_blueprint(realtime_report_bp, url_prefix='/api/realtime-analysis/reports')
    app.register_blueprint(websocket_api_bp, url_prefix='/api/websocket')
    app.register_blueprint(ml_factor_routes)
    app.register_blueprint(realtime_analysis_routes)
    
    from app.main import main_bp
    app.register_blueprint(main_bp)
    
    # 注册WebSocket事件处理器
    from app.websocket import websocket_events
    
    return app 