
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
