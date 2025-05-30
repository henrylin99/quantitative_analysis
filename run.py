#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from app import create_app
from app.extensions import socketio

# 创建Flask应用实例
app = create_app(os.getenv('FLASK_ENV', 'default'))

if __name__ == '__main__':
    # 开发环境下运行，使用SocketIO
    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    ) 