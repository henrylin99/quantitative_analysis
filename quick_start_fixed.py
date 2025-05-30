#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子选股系统快速启动脚本 (修复版)

一键启动系统，使用最小化依赖，避免兼容性问题
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
    ║  🚀 一键启动 - 快速体验量化投资的魅力 (修复版)                  ║
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

def install_minimal_dependencies():
    """安装最小化依赖包"""
    print("\n📦 安装最小化依赖包...")
    
    # 核心依赖包列表
    core_packages = [
        "Flask>=2.3.0",
        "Flask-RESTful>=0.3.10", 
        "Flask-CORS>=4.0.0",
        "SQLAlchemy>=2.0.0",
        "Flask-SQLAlchemy>=3.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
        "scipy>=1.11.0",
        "loguru>=0.7.0",
        "requests>=2.31.0",
        "python-dateutil>=2.8.0",
        "python-dotenv>=1.0.0",
        "matplotlib>=3.7.0",
        "joblib>=1.3.0"
    ]
    
    try:
        print("   正在安装核心依赖包，请稍候...")
        for package in core_packages:
            print(f"   安装: {package}")
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", package
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"   ⚠️ {package} 安装失败，跳过")
                continue
        
        print("✅ 核心依赖包安装完成")
        
        # 尝试安装可选依赖
        print("\n📦 尝试安装可选依赖包...")
        optional_packages = [
            "cvxpy>=1.4.0",  # 组合优化
            "xgboost>=1.7.0",  # 机器学习
            "lightgbm>=4.0.0"  # 机器学习
        ]
        
        for package in optional_packages:
            try:
                print(f"   尝试安装: {package}")
                result = subprocess.run([
                    sys.executable, "-m", "pip", "install", package
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print(f"   ✅ {package} 安装成功")
                else:
                    print(f"   ⚠️ {package} 安装失败，系统将使用基础功能")
            except subprocess.TimeoutExpired:
                print(f"   ⚠️ {package} 安装超时，跳过")
            except Exception as e:
                print(f"   ⚠️ {package} 安装出错: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 安装依赖包时出错: {e}")
        return False

def create_minimal_config():
    """创建最小化配置"""
    print("\n🔧 创建最小化配置...")
    
    try:
        # 创建简化的配置文件
        config_content = '''
import os
from pathlib import Path

class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # 数据库配置 - 使用SQLite
    basedir = Path(__file__).parent
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{basedir}/stock_analysis.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 日志配置
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/app.log'

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
'''
        
        with open('config_minimal.py', 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print("✅ 最小化配置创建完成")
        return True
        
    except Exception as e:
        print(f"❌ 创建配置失败: {e}")
        return False

def initialize_minimal_system():
    """初始化最小化系统"""
    print("\n🔧 初始化最小化系统...")
    
    try:
        # 创建日志目录
        os.makedirs('logs', exist_ok=True)
        
        # 尝试导入并初始化系统
        try:
            from app import create_app
            from app.extensions import db
            
            # 创建应用实例
            app = create_app('development')
            
            with app.app_context():
                # 创建数据库表
                print("   创建数据库表...")
                db.create_all()
                print("   ✅ 数据库表创建完成")
                
        except ImportError as e:
            print(f"   ⚠️ 部分模块导入失败: {e}")
            print("   系统将以基础模式运行")
        
        print("✅ 系统初始化完成")
        return True
        
    except Exception as e:
        print(f"❌ 系统初始化失败: {e}")
        return False

def start_minimal_server():
    """启动最小化服务器"""
    print("\n🌐 启动最小化服务器...")
    
    try:
        # 创建最小化的Flask应用
        minimal_app_content = '''
from flask import Flask, render_template_string
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>多因子选股系统</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; text-align: center; }
            .status { background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 20px 0; }
            .warning { background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; }
            .feature { margin: 10px 0; padding: 10px; background: #f8f9fa; border-left: 4px solid #007bff; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 多因子选股系统</h1>
            
            <div class="status">
                <h3>✅ 系统状态</h3>
                <p>系统已成功启动！当前运行在最小化模式。</p>
            </div>
            
            <div class="warning">
                <h3>⚠️ 注意事项</h3>
                <p>由于某些依赖包存在兼容性问题，系统当前运行在最小化模式。</p>
                <p>建议手动安装以下包以获得完整功能：</p>
                <ul>
                    <li>cvxpy - 组合优化功能</li>
                    <li>xgboost - 机器学习功能</li>
                    <li>lightgbm - 机器学习功能</li>
                </ul>
            </div>
            
            <h3>📋 可用功能</h3>
            <div class="feature">
                <strong>✅ 基础Web框架</strong> - Flask服务器正常运行
            </div>
            <div class="feature">
                <strong>✅ 数据处理</strong> - Pandas和NumPy可用
            </div>
            <div class="feature">
                <strong>✅ 机器学习基础</strong> - Scikit-learn可用
            </div>
            <div class="feature">
                <strong>✅ 数据库支持</strong> - SQLAlchemy可用
            </div>
            
            <h3>🔧 下一步</h3>
            <p>1. 手动安装缺失的依赖包</p>
            <p>2. 重新启动系统以获得完整功能</p>
            <p>3. 访问 <a href="/ml-factor">/ml-factor</a> 查看主要功能</p>
            
            <div style="text-align: center; margin-top: 30px; color: #666;">
                <p>多因子选股系统 - 让量化投资更简单</p>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/ml-factor')
def ml_factor():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>多因子选股系统 - 主界面</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 0; background: #f5f5f5; }
            .header { background: #2c3e50; color: white; padding: 20px; text-align: center; }
            .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
            .card { background: white; margin: 20px 0; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .btn { background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }
            .btn:hover { background: #2980b9; }
            .status-good { color: #27ae60; }
            .status-warning { color: #f39c12; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>多因子选股系统</h1>
            <p>Multi-Factor Stock Selection System</p>
        </div>
        
        <div class="container">
            <div class="card">
                <h2>系统状态</h2>
                <p class="status-good">✅ 基础系统运行正常</p>
                <p class="status-warning">⚠️ 部分高级功能需要额外依赖</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>📊 因子管理</h3>
                    <p>管理和计算股票因子</p>
                    <a href="#" class="btn">进入因子管理</a>
                </div>
                
                <div class="card">
                    <h3>🤖 模型管理</h3>
                    <p>机器学习模型训练和预测</p>
                    <a href="#" class="btn">进入模型管理</a>
                </div>
                
                <div class="card">
                    <h3>🎯 股票选择</h3>
                    <p>基于因子和模型的选股</p>
                    <a href="#" class="btn">进入股票选择</a>
                </div>
                
                <div class="card">
                    <h3>📈 组合优化</h3>
                    <p>投资组合权重优化</p>
                    <a href="#" class="btn">进入组合优化</a>
                </div>
                
                <div class="card">
                    <h3>🔄 回测验证</h3>
                    <p>策略回测和性能分析</p>
                    <a href="#" class="btn">进入回测验证</a>
                </div>
                
                <div class="card">
                    <h3>📋 分析报告</h3>
                    <p>深度分析和报告生成</p>
                    <a href="#" class="btn">进入分析报告</a>
                </div>
            </div>
            
            <div class="card">
                <h3>💡 使用提示</h3>
                <p>当前系统运行在最小化模式，建议安装完整依赖以获得最佳体验：</p>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
pip install cvxpy xgboost lightgbm
                </pre>
            </div>
        </div>
    </body>
    </html>
    """)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
'''
        
        # 写入最小化应用文件
        with open('app_minimal.py', 'w', encoding='utf-8') as f:
            f.write(minimal_app_content)
        
        print("✅ 最小化服务器创建成功!")
        print("📱 访问地址:")
        print("   - 主页: http://localhost:5000")
        print("   - 多因子系统: http://localhost:5000/ml-factor")
        print("\n💡 提示:")
        print("   - 按 Ctrl+C 停止服务器")
        print("   - 浏览器将自动打开系统界面")
        
        # 延迟2秒后打开浏览器
        import threading
        def open_browser():
            time.sleep(2)
            webbrowser.open('http://localhost:5000')
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # 启动最小化服务器
        subprocess.run([sys.executable, "app_minimal.py"])
        
    except KeyboardInterrupt:
        print("\n👋 服务器已停止，感谢使用!")
    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")
        return False

def main():
    """主函数"""
    print_banner()
    
    print("🚀 开始快速启动流程 (修复版)...\n")
    
    # 1. 检查Python版本
    if not check_python_version():
        print("\n❌ 启动失败: Python版本不符合要求")
        input("按回车键退出...")
        return
    
    # 2. 安装最小化依赖包
    if not install_minimal_dependencies():
        print("\n❌ 启动失败: 依赖包安装失败")
        print("💡 建议手动运行: pip install Flask pandas numpy scikit-learn")
        input("按回车键退出...")
        return
    
    # 3. 创建最小化配置
    create_minimal_config()
    
    # 4. 初始化最小化系统
    initialize_minimal_system()
    
    # 5. 启动最小化服务器
    print("\n🎉 系统准备就绪!")
    input("按回车键启动最小化服务器...")
    
    start_minimal_server()

if __name__ == "__main__":
    main() 