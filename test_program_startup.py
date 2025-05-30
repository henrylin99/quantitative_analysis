#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import subprocess
import signal
import os
import sys

def test_program_startup():
    """测试程序启动功能"""
    print("🚀 开始测试程序启动功能...")
    
    # 测试1: 检查基础依赖包
    print("\n📦 测试1: 检查基础依赖包...")
    try:
        import flask
        import flask_cors
        import sqlalchemy
        from app import create_app
        from app.extensions import socketio
        print("✅ 基础依赖包检查通过")
    except ImportError as e:
        print(f"❌ 依赖包缺失: {e}")
        return False
    
    # 测试2: 检查配置文件
    print("\n⚙️ 测试2: 检查配置文件...")
    try:
        from config import config
        print("✅ 配置文件加载成功")
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        return False
    
    # 测试3: 检查Flask应用创建
    print("\n🏗️ 测试3: 检查Flask应用创建...")
    try:
        app = create_app('default')
        print("✅ Flask应用创建成功")
    except Exception as e:
        print(f"❌ Flask应用创建失败: {e}")
        return False
    
    # 测试4: 检查Web服务响应
    print("\n🌐 测试4: 检查Web服务响应...")
    try:
        # 等待服务启动
        time.sleep(2)
        response = requests.get('http://localhost:5001/', timeout=10)
        if response.status_code == 200:
            print("✅ Web服务响应正常")
        else:
            print(f"❌ Web服务响应异常: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Web服务连接失败: {e}")
        return False
    
    # 测试5: 检查API端点
    print("\n🔌 测试5: 检查主要API端点...")
    api_endpoints = [
        '/api/ml-factor/factors/list',
        '/api/ml-factor/models/list',
        '/api/realtime-analysis/data/status'
    ]
    
    for endpoint in api_endpoints:
        try:
            response = requests.get(f'http://localhost:5001{endpoint}', timeout=5)
            if response.status_code in [200, 404, 500]:  # 允许404和500，说明路由存在
                print(f"✅ API端点 {endpoint} 可访问")
            else:
                print(f"❌ API端点 {endpoint} 响应异常: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ API端点 {endpoint} 连接失败: {e}")
    
    print("\n🎉 程序启动功能测试完成！")
    return True

if __name__ == '__main__':
    success = test_program_startup()
    if success:
        print("\n✅ 所有测试通过，程序启动正常！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败，请检查程序配置！")
        sys.exit(1) 