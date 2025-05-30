#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子选股系统启动脚本

功能：
1. 检查环境依赖
2. 初始化数据库
3. 启动Web服务
4. 提供系统管理功能
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

from app import create_app
from app.extensions import db
from app.services.factor_engine import FactorEngine
from config import config


class SystemManager:
    """系统管理器"""
    
    def __init__(self):
        self.app = None
        self.factor_engine = None
        
    def check_dependencies(self):
        """检查系统依赖"""
        print("检查系统依赖...")
        
        # 检查Python版本
        python_version = sys.version_info
        if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
            print("❌ Python版本过低，需要Python 3.8+")
            return False
        print(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        # 检查必需的包
        required_packages = [
            'flask', 'sqlalchemy', 'pandas', 'numpy', 'scikit-learn',
            'xgboost', 'lightgbm', 'cvxpy', 'loguru', 'requests'
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
                print(f"✅ {package}")
            except ImportError:
                missing_packages.append(package)
                print(f"❌ {package}")
        
        if missing_packages:
            print(f"\n缺少以下包，请运行: pip install {' '.join(missing_packages)}")
            return False
        
        print("✅ 所有依赖检查通过")
        return True
    
    def setup_database(self):
        """设置数据库"""
        print("\n初始化数据库...")
        
        try:
            # 创建应用实例
            self.app = create_app('development')
            
            with self.app.app_context():
                # 创建所有表
                db.create_all()
                print("✅ 数据库表创建完成")
                
                # 初始化因子引擎
                self.factor_engine = FactorEngine()
                
                # 创建内置因子定义
                self._create_builtin_factors()
                
                print("✅ 数据库初始化完成")
                return True
                
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            return False
    
    def _create_builtin_factors(self):
        """创建内置因子定义"""
        print("创建内置因子定义...")
        
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
                'factor_id': 'momentum_20d',
                'factor_name': '20日动量',
                'factor_type': 'momentum',
                'factor_formula': 'close.pct_change(20)',
                'description': '20日价格变化率'
            },
            {
                'factor_id': 'volatility_20d',
                'factor_name': '20日波动率',
                'factor_type': 'volatility',
                'factor_formula': 'close.pct_change().rolling(20).std()',
                'description': '20日收益率标准差'
            },
            {
                'factor_id': 'rsi_14',
                'factor_name': 'RSI指标',
                'factor_type': 'technical',
                'factor_formula': 'talib.RSI(close, timeperiod=14)',
                'description': '14日相对强弱指标'
            },
            {
                'factor_id': 'turnover_rate',
                'factor_name': '换手率',
                'factor_type': 'volume',
                'factor_formula': 'vol / float_share',
                'description': '成交量/流通股本'
            },
            {
                'factor_id': 'pe_ratio',
                'factor_name': '市盈率',
                'factor_type': 'fundamental',
                'factor_formula': 'total_mv / net_profit_ttm',
                'description': '总市值/净利润TTM'
            },
            {
                'factor_id': 'pb_ratio',
                'factor_name': '市净率',
                'factor_type': 'fundamental',
                'factor_formula': 'total_mv / total_owner_equities',
                'description': '总市值/净资产'
            },
            {
                'factor_id': 'roe',
                'factor_name': '净资产收益率',
                'factor_type': 'fundamental',
                'factor_formula': 'net_profit_ttm / total_owner_equities',
                'description': '净利润TTM/净资产'
            },
            {
                'factor_id': 'debt_ratio',
                'factor_name': '资产负债率',
                'factor_type': 'fundamental',
                'factor_formula': 'total_liab / total_assets',
                'description': '总负债/总资产'
            },
            {
                'factor_id': 'current_ratio',
                'factor_name': '流动比率',
                'factor_type': 'fundamental',
                'factor_formula': 'total_cur_assets / total_cur_liab',
                'description': '流动资产/流动负债'
            },
            {
                'factor_id': 'gross_margin',
                'factor_name': '毛利率',
                'factor_type': 'fundamental',
                'factor_formula': '(revenue - oper_cost) / revenue',
                'description': '(营业收入-营业成本)/营业收入'
            }
        ]
        
        created_count = 0
        for factor_config in builtin_factors:
            try:
                success = self.factor_engine.create_factor_definition(**factor_config)
                if success:
                    created_count += 1
                    print(f"  ✅ {factor_config['factor_id']}")
                else:
                    print(f"  ⚠️ {factor_config['factor_id']} (可能已存在)")
            except Exception as e:
                print(f"  ❌ {factor_config['factor_id']}: {e}")
        
        print(f"✅ 创建了 {created_count} 个内置因子")
    
    def start_web_server(self, host='127.0.0.1', port=5000, debug=True):
        """启动Web服务器"""
        print(f"\n启动Web服务器...")
        print(f"地址: http://{host}:{port}")
        print(f"前端界面: http://{host}:{port}/ml-factor")
        print("按 Ctrl+C 停止服务器")
        
        try:
            if not self.app:
                self.app = create_app('development')
            
            # 自动打开浏览器
            if not debug:
                webbrowser.open(f'http://{host}:{port}/ml-factor')
            
            # 启动服务器
            self.app.run(host=host, port=port, debug=debug)
            
        except KeyboardInterrupt:
            print("\n服务器已停止")
        except Exception as e:
            print(f"❌ 启动服务器失败: {e}")
    
    def run_demo(self):
        """运行演示"""
        print("\n启动系统演示...")
        
        try:
            # 启动演示脚本
            demo_script = project_root / "examples" / "complete_system_example.py"
            if demo_script.exists():
                subprocess.run([sys.executable, str(demo_script)])
            else:
                print("❌ 演示脚本不存在")
        except Exception as e:
            print(f"❌ 运行演示失败: {e}")
    
    def show_system_info(self):
        """显示系统信息"""
        print("\n" + "="*60)
        print("多因子选股系统")
        print("="*60)
        print("功能模块:")
        print("  📊 因子管理 - 内置12个因子，支持自定义因子")
        print("  🤖 模型管理 - 支持随机森林、XGBoost、LightGBM")
        print("  🎯 股票选择 - 基于因子和ML模型的选股")
        print("  📈 组合优化 - 等权重、均值-方差、风险平价等")
        print("  🔄 回测验证 - 完整的策略回测和比较")
        print("  📋 分析报告 - 行业分析、因子贡献度分析")
        print("\nAPI接口:")
        print("  🌐 REST API - 完整的程序化接口")
        print("  💻 Web界面 - 现代化的前端操作界面")
        print("\n技术栈:")
        print("  🐍 Python 3.8+ / Flask / SQLAlchemy")
        print("  📊 Pandas / NumPy / Scikit-learn")
        print("  🚀 XGBoost / LightGBM / CVXPY")
        print("  🎨 Bootstrap 5 / JavaScript")
        print("="*60)


def main():
    """主函数"""
    manager = SystemManager()
    
    print("多因子选股系统启动器")
    print("="*40)
    
    while True:
        print("\n请选择操作:")
        print("1. 检查系统依赖")
        print("2. 初始化数据库")
        print("3. 启动Web服务器")
        print("4. 启动Web服务器(生产模式)")
        print("5. 运行系统演示")
        print("6. 显示系统信息")
        print("0. 退出")
        
        choice = input("\n请输入选择 (0-6): ").strip()
        
        if choice == '0':
            print("再见！")
            break
        elif choice == '1':
            manager.check_dependencies()
        elif choice == '2':
            manager.setup_database()
        elif choice == '3':
            manager.start_web_server(debug=True)
        elif choice == '4':
            manager.start_web_server(debug=False)
        elif choice == '5':
            manager.run_demo()
        elif choice == '6':
            manager.show_system_info()
        else:
            print("无效选择，请重新输入")


if __name__ == "__main__":
    main() 