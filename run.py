#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用启动入口。

SOCKETIO_ASYNC_MODE=eventlet 时必须先 monkey_patch 再导入应用模块
（阻塞调用依赖补丁协作），因此这段逻辑放在所有 app 导入之前。
"""

import os

if os.getenv('SOCKETIO_ASYNC_MODE', 'threading') == 'eventlet':
    import eventlet

    eventlet.monkey_patch()

from app import create_app
from app.extensions import socketio
from startup_runtime import build_health_report, build_health_summary_lines, build_startup_report, inspect_parquet_data_assets

# 创建Flask应用实例（FLASK_ENV 可选值见 config.py: development/production/testing）
app = create_app(os.getenv('FLASK_ENV', 'default'))


def inspect_runtime_health(flask_app):
    with flask_app.app_context():
        data_dir = flask_app.config.get("DATA_DIR")
        connected, existing_assets, non_empty_assets = inspect_parquet_data_assets(data_dir)

        return build_health_report(
            flask_app.config,
            connected=connected,
            existing_tables=existing_assets,
            non_empty_tables=non_empty_assets,
        )

if __name__ == '__main__':
    print("启动检查:")
    for line in build_startup_report(app.config):
        print(f"  - {line}")
    for line in build_health_summary_lines(inspect_runtime_health(app)):
        print(line)

    # 大宽表状态检查
    with app.app_context():
        from app.services.wide_table_status import should_update_wide_table
        need_update, reason = should_update_wide_table(app.config.get("DATA_DIR"))
        tag = "⚠️" if need_update else "✅"
        print(f"  {tag} 大宽表: {reason}")

    is_debug = bool(app.config.get('DEBUG'))
    if is_debug:
        print("⚠️  以 DEBUG 模式运行开发服务器，请勿用于生产环境")

    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=is_debug,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )
