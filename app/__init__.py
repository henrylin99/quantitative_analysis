import os

from runtime_compat import ensure_click_parameter_source

ensure_click_parameter_source()

from flask import Flask, jsonify, request
from flask_cors import CORS
from config import config  # noqa: F401
from app.extensions import db, socketio
from app.utils.logger import setup_logger


def _install_api_token_guard(app: Flask) -> None:
    """API 数据面门禁：设置 API_AUTH_TOKEN 后，所有 /api/* 请求（含 GET）
    必须携带 X-API-Token 头或 Authorization: Bearer <token>。

    会话、查询历史、任务结果等数据同样受保护，避免匿名读取。
    未设置时保持原行为（本机单人使用，无鉴权；生产配置会强制要求设置）。
    浏览器直连场景请通过反向代理注入该头（如 nginx proxy_set_header）。
    """
    token = (os.getenv('API_AUTH_TOKEN') or '').strip()
    if not token:
        return

    @app.before_request
    def _require_api_token():
        # CORS 预检请求不带 Token（浏览器规范），必须放行交给 Flask-CORS 处理，
        # 否则带 Token 的跨域调用会在预检阶段被 401 拦死
        if request.method == 'OPTIONS':
            return None
        # socket.io 走 POST 轮询握手，浏览器端无法携带自定义头；
        # 推送通道本身受同源策略约束，不在此设防
        if not request.path.startswith('/api/') or request.path.startswith('/socket.io'):
            return None
        provided = request.headers.get('X-API-Token', '')
        auth_header = request.headers.get('Authorization', '')
        if not provided and auth_header.startswith('Bearer '):
            provided = auth_header[len('Bearer '):]
        if provided != token:
            return jsonify({'success': False, 'error': '未授权：缺少或错误的 API Token'}), 401
        return None



def _ensure_data_dir_skeleton(app: Flask) -> None:
    """创建 data/ 下的 parquet 分区骨架目录（存在即跳过）。

    覆盖 ParquetDataReader.TABLE_DIRS 的日频分区目录、index_daily 分区，
    以及各 ParquetStateStore/EventStore 使用的状态目录；全部 mkdir 幂等。
    """
    import os
    from pathlib import Path

    data_dir = Path(os.getenv("DATA_DIR") or Path(app.root_path).parent / "data")
    subdirs = [
        # 日频 hive 分区（TABLE_DIRS 值）；stk_factor/cyq_perf 已摘出同步链路，
        # 空库不再预建骨架目录（表目录在读到数据时按需创建）
        "daily_history/daily", "daily_basic/daily",
        "adj_factor/daily", "moneyflow/daily",
        "income_statement", "balance_sheet", "cash_flow",
        "index_daily/stock",
        # 状态/事件存储目录
        "data_job_state", "minute_sync", "ml_factor_state", "ml_factor_state/factor_values",
        "paper_trading", "alerts", "cache", "config",
    ]
    for sub in subdirs:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    app.logger.info("数据目录骨架已就绪: %s", data_dir)


def create_app(config_name='default'):
    """应用工厂函数"""
    from config import config as config_map

    if config_name not in config_map:
        raise ValueError(
            f"未知的配置名: {config_name!r}，可选值: {sorted(config_map.keys())}"
        )

    app = Flask(__name__)

    # 加载配置
    app.config.from_object(config_map[config_name])

    # 生产环境强制校验（SECRET_KEY 等），配置不完整直接失败而不是带病启动
    validator = getattr(config_map[config_name], 'validate', None)
    if callable(validator):
        validator(app.config)

    # 初始化扩展
    db.init_app(app)
    cors_origins = app.config.get('CORS_ORIGINS', '*')
    socketio.init_app(app, cors_allowed_origins=cors_origins)
    CORS(app, origins=cors_origins)
    
    # 设置日志
    setup_logger(app.config['LOG_LEVEL'], app.config['LOG_FILE'])

    # 可选写操作 Token 门禁（API_AUTH_TOKEN 未设置时不生效）
    _install_api_token_guard(app)

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
    from app.api.data_jobs_api import data_jobs_bp
    from app.api.ai_assistant_api import ai_assistant_bp
    from app.routes.ml_factor_routes import ml_factor_routes
    from app.routes.realtime_analysis_routes import realtime_analysis_routes
    from app.routes.heatmap import heatmap_routes
    from app.routes.pattern_screen import pattern_screen_bp
    from app.api.pattern_screen_api import pattern_screen_api
    from app.api.market_api import market_bp, datasources_bp
    from app.api.research_api import research_bp
    from app.api.fund_api import fund_bp
    from app.api.paper_trading_api import paper_trading_bp
    from app.api.hk_stock_api import hk_stock_api
    from app.api.us_stock_api import us_stock_api
    from app.api.us_analytics_api import us_analytics_api
    from app.api.hk_analytics_api import hk_analytics_api
    from app.api.insights_api import insights_api
    from app.api.strategy_guardian_api import strategy_guardian_bp
    from app.api.settings_api import settings_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(ml_factor_bp)
    app.register_blueprint(text2sql_bp)
    app.register_blueprint(realtime_analysis_bp)
    app.register_blueprint(realtime_indicators_bp, url_prefix='/api/realtime-analysis/indicators')
    app.register_blueprint(realtime_signals_bp, url_prefix='/api/realtime-analysis/signals')
    app.register_blueprint(realtime_monitor_bp, url_prefix='/api/realtime-analysis/monitor')
    app.register_blueprint(realtime_risk_bp, url_prefix='/api/realtime-analysis/risk')
    app.register_blueprint(realtime_report_bp, url_prefix='/api/realtime-analysis/reports')
    from app.api.realtime_auction import realtime_auction_bp
    app.register_blueprint(realtime_auction_bp, url_prefix='/api/realtime-analysis/auction')
    app.register_blueprint(websocket_api_bp, url_prefix='/api/websocket')
    app.register_blueprint(data_jobs_bp)
    app.register_blueprint(ai_assistant_bp)
    app.register_blueprint(ml_factor_routes)
    app.register_blueprint(realtime_analysis_routes)
    app.register_blueprint(heatmap_routes)
    app.register_blueprint(pattern_screen_bp)
    app.register_blueprint(pattern_screen_api)
    app.register_blueprint(market_bp)
    app.register_blueprint(datasources_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(fund_bp)
    app.register_blueprint(paper_trading_bp, url_prefix='/api/paper-trading')
    app.register_blueprint(hk_stock_api)
    app.register_blueprint(us_stock_api)
    app.register_blueprint(us_analytics_api)
    app.register_blueprint(hk_analytics_api)
    app.register_blueprint(insights_api)
    app.register_blueprint(strategy_guardian_bp, url_prefix='/api/strategy-guardian')
    app.register_blueprint(settings_bp)

    from app.main import main_bp
    app.register_blueprint(main_bp)
    
    # 注册WebSocket事件处理器
    from app.websocket import websocket_events  # noqa: F401

    # 启动自举（幂等）：建全部 SQLite ORM 表 + data/ 下 parquet 分区骨架目录。
    # 空库从零启动时避免各 API 首次访问报 no such table；骨架目录让分区扫描
    # 代码与数据管理页面对"从未下载"状态有稳定目录可查。失败只告警不阻塞启动。
    with app.app_context():
        try:
            # 显式导入全部模型模块（create_all 只处理已 import 的模型；
            # 正常路径蓝图注册已传递导入，这里兜底保证空库场景全覆盖。
            # 注意勿用 `import app.models`——会在函数局部把 app 绑定回包模块）
            import importlib

            importlib.import_module("app.models")
            for _m in (
                "app.models.realtime_indicator",
                "app.models.risk_alert",
                "app.models.realtime_report",
                "app.models.portfolio_position",
                "app.models.trading_signal",
            ):
                importlib.import_module(_m)
            db.create_all()
        except Exception:
            app.logger.warning("启动建 SQLite 表失败（不阻塞应用启动）", exc_info=True)

        try:
            _ensure_data_dir_skeleton(app)
        except Exception:
            app.logger.warning("启动创建数据目录骨架失败（不阻塞应用启动）", exc_info=True)

    # 启动时按超时口径清理僵尸数据任务：run 超过 DATA_JOB_TIMEOUT 仍停在
    # pending/queued/running 判定为 worker 中断遗留。不用"启动即清空"是因为
    # 多 worker 部署下其他进程可能有任务正在执行，会被误杀。
    with app.app_context():
        try:
            from app.services.data_jobs.parquet_state_store import ParquetDataJobStateStore

            reaped = ParquetDataJobStateStore().reap_stale_runs()
            if reaped:
                app.logger.warning(
                    "启动清理僵尸数据任务 %d 个（标记为 failed）: %s",
                    len(reaped), [r.id for r in reaped],
                )
        except Exception:
            app.logger.warning("启动清理僵尸数据任务失败（不阻塞应用启动）", exc_info=True)

    # 每日收盘后定时扫描（筹码信号/regime/行业轮动/财务异动 → 预警记录）。
    # 测试环境不启动；多 worker 部署由 run_scan 的同日去重兜底。
    if not app.config.get("TESTING") and os.getenv("DAILY_ALERT_ENABLED", "1") != "0":
        try:
            from app.services.daily_alert_service import DailyAlertScheduler

            DailyAlertScheduler.instance().start()
        except Exception:
            app.logger.warning("每日预警调度线程启动失败（不阻塞应用启动）", exc_info=True)

    return app

