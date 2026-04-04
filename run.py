#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from app import create_app
from app.extensions import db
from app.extensions import socketio
from sqlalchemy import inspect
from startup_runtime import build_health_report, build_health_summary_lines, build_startup_report

# 创建Flask应用实例
app = create_app(os.getenv('FLASK_ENV', 'default'))


def inspect_runtime_health(flask_app):
    with flask_app.app_context():
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
            flask_app.config,
            connected=connected,
            existing_tables=existing_tables,
            non_empty_tables=non_empty_tables,
        )

if __name__ == '__main__':
    print("启动检查:")
    for line in build_startup_report(app.config):
        print(f"  - {line}")
    for line in build_health_summary_lines(inspect_runtime_health(app)):
        print(line)

    # 开发环境下运行，使用SocketIO
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    ) 
