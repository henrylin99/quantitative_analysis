#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from app import create_app
from app.extensions import socketio
from startup_runtime import build_startup_report

# 创建Flask应用实例
app = create_app(os.getenv('FLASK_ENV', 'default'))

if __name__ == '__main__':
    print("启动检查:")
    for line in build_startup_report(app.config):
        print(f"  - {line}")

    # 开发环境下运行，使用SocketIO
    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    ) 
