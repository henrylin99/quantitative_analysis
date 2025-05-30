#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子选股系统快速启动脚本

一键启动系统，自动完成环境检查、数据库初始化和服务启动
"""

import os
import sys
import subprocess
import time
import webbrowser
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def print_banner():
    """打印系统横幅"""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                    多因子选股系统                              ║
    ║                Multi-Factor Stock Selection System           ║
    ║                                                              ║
    ║  🚀 一键启动 - 快速体验量化投资的魅力                          ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def check_python_version():
    """检查Python版本"""
    print("🔍 检查Python版本...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python版本过低，需要Python 3.8+")
        print(f"   当前版本: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python版本检查通过: {version.major}.{version.minor}.{version.micro}")
    return True

def install_dependencies():
    """安装依赖包"""
    print("\n📦 检查并安装依赖包...")
    
    try:
        # 检查requirements.txt是否存在
        requirements_file = project_root / "requirements.txt"
        if not requirements_file.exists():
            print("❌ requirements.txt文件不存在")
            return False
        
        # 安装依赖
        print("   正在安装依赖包，请稍候...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ 依赖包安装完成")
            return True
        else:
            print("❌ 依赖包安装失败:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ 安装依赖包时出错: {e}")
        return False

def initialize_system():
    """初始化系统"""
    print("\n🔧 初始化系统...")
    
    try:
        from app import create_app
        from app.extensions import db
        from app.services.factor_engine import FactorEngine
        
        # 创建应用实例
        app = create_app('development')
        
        with app.app_context():
            # 创建数据库表
            print("   创建数据库表...")
            db.create_all()
            
            # 初始化因子引擎
            print("   初始化因子引擎...")
            factor_engine = FactorEngine()
            
            # 创建内置因子（简化版）
            print("   创建内置因子...")
            builtin_factors = [
                {
                    'factor_id': 'momentum_1d',
                    'factor_name': '1日动量',
                    'factor_type': 'momentum',
                    'factor_formula': 'close.pct_change(1)',
                    'description': '1日价格变化率'
                },
                {
                    'factor_id': 'momentum_5d',
                    'factor_name': '5日动量',
                    'factor_type': 'momentum',
                    'factor_formula': 'close.pct_change(5)',
                    'description': '5日价格变化率'
                },
                {
                    'factor_id': 'volatility_20d',
                    'factor_name': '20日波动率',
                    'factor_type': 'volatility',
                    'factor_formula': 'close.pct_change().rolling(20).std()',
                    'description': '20日收益率标准差'
                }
            ]
            
            for factor_config in builtin_factors:
                try:
                    factor_engine.create_factor_definition(**factor_config)
                except:
                    pass  # 忽略已存在的因子
            
        print("✅ 系统初始化完成")
        return True
        
    except Exception as e:
        print(f"❌ 系统初始化失败: {e}")
        return False

def start_web_server():
    """启动Web服务器"""
    print("\n🌐 启动Web服务器...")
    
    try:
        from app import create_app
        
        app = create_app('development')
        
        print("✅ Web服务器启动成功!")
        print("📱 访问地址:")
        print("   - 主页: http://localhost:5000")
        print("   - 多因子系统: http://localhost:5000/ml-factor")
        print("   - API文档: http://localhost:5000/api")
        print("\n💡 提示:")
        print("   - 按 Ctrl+C 停止服务器")
        print("   - 浏览器将自动打开系统界面")
        
        # 延迟2秒后打开浏览器
        import threading
        def open_browser():
            time.sleep(2)
            webbrowser.open('http://localhost:5000/ml-factor')
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # 启动服务器
        app.run(host='127.0.0.1', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("\n👋 服务器已停止，感谢使用!")
    except Exception as e:
        print(f"❌ 启动Web服务器失败: {e}")
        return False

def main():
    """主函数"""
    print_banner()
    
    print("🚀 开始快速启动流程...\n")
    
    # 1. 检查Python版本
    if not check_python_version():
        print("\n❌ 启动失败: Python版本不符合要求")
        input("按回车键退出...")
        return
    
    # 2. 安装依赖包
    if not install_dependencies():
        print("\n❌ 启动失败: 依赖包安装失败")
        print("💡 建议手动运行: pip install -r requirements.txt")
        input("按回车键退出...")
        return
    
    # 3. 初始化系统
    if not initialize_system():
        print("\n❌ 启动失败: 系统初始化失败")
        input("按回车键退出...")
        return
    
    # 4. 启动Web服务器
    print("\n🎉 系统准备就绪!")
    input("按回车键启动Web服务器...")
    
    start_web_server()

if __name__ == "__main__":
    main() 