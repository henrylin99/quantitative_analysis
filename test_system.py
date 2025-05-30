#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多因子选股系统测试脚本

快速验证系统的核心功能是否正常工作
"""

import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试核心模块导入"""
    print("🔍 测试核心模块导入...")
    
    tests = [
        ("Flask", "from flask import Flask"),
        ("Pandas", "import pandas as pd"),
        ("NumPy", "import numpy as np"),
        ("SQLAlchemy", "from sqlalchemy import create_engine"),
        ("Scikit-learn", "from sklearn.ensemble import RandomForestRegressor"),
        ("Scipy", "from scipy import stats"),
        ("Loguru", "from loguru import logger"),
        ("Requests", "import requests"),
        ("Matplotlib", "import matplotlib.pyplot as plt"),
    ]
    
    results = {}
    for name, import_stmt in tests:
        try:
            exec(import_stmt)
            print(f"  ✅ {name}")
            results[name] = True
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            results[name] = False
        except Exception as e:
            print(f"  ⚠️ {name}: {e}")
            results[name] = False
    
    return results

def test_optional_imports():
    """测试可选模块导入"""
    print("\n🔍 测试可选模块导入...")
    
    optional_tests = [
        ("XGBoost", "import xgboost as xgb"),
        ("LightGBM", "import lightgbm as lgb"),
        ("CVXPY", "import cvxpy as cp"),
    ]
    
    results = {}
    for name, import_stmt in optional_tests:
        try:
            exec(import_stmt)
            print(f"  ✅ {name}")
            results[name] = True
        except ImportError:
            print(f"  ⚠️ {name}: 未安装（可选）")
            results[name] = False
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            results[name] = False
    
    return results

def test_app_creation():
    """测试应用创建"""
    print("\n🔍 测试应用创建...")
    
    try:
        from app import create_app
        app = create_app('development')
        print("  ✅ Flask应用创建成功")
        return True
    except Exception as e:
        print(f"  ❌ Flask应用创建失败: {e}")
        traceback.print_exc()
        return False

def test_database_connection():
    """测试数据库连接"""
    print("\n🔍 测试数据库连接...")
    
    try:
        from app import create_app
        from app.extensions import db
        
        app = create_app('development')
        with app.app_context():
            # 尝试创建表
            db.create_all()
            print("  ✅ 数据库连接和表创建成功")
            return True
    except Exception as e:
        print(f"  ❌ 数据库连接失败: {e}")
        return False

def test_services():
    """测试核心服务"""
    print("\n🔍 测试核心服务...")
    
    services_tests = [
        ("因子引擎", "from app.services.factor_engine import FactorEngine"),
        ("ML模型管理器", "from app.services.ml_models import MLModelManager"),
        ("股票打分引擎", "from app.services.stock_scoring import StockScoringEngine"),
        ("组合优化器", "from app.services.portfolio_optimizer import PortfolioOptimizer"),
        ("回测引擎", "from app.services.backtest_engine import BacktestEngine"),
    ]
    
    results = {}
    for name, import_stmt in services_tests:
        try:
            exec(import_stmt)
            print(f"  ✅ {name}")
            results[name] = True
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            results[name] = False
        except Exception as e:
            print(f"  ⚠️ {name}: {e}")
            results[name] = False
    
    return results

def test_basic_functionality():
    """测试基础功能"""
    print("\n🔍 测试基础功能...")
    
    try:
        import pandas as pd
        import numpy as np
        
        # 测试数据处理
        df = pd.DataFrame({
            'close': [100, 101, 102, 103, 104],
            'volume': [1000, 1100, 1200, 1300, 1400]
        })
        
        # 测试简单因子计算
        df['momentum_1d'] = df['close'].pct_change(1)
        df['volume_ma'] = df['volume'].rolling(3).mean()
        
        print("  ✅ 基础数据处理功能正常")
        
        # 测试机器学习
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import train_test_split
        
        X = np.random.rand(100, 5)
        y = np.random.rand(100)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
        
        model = RandomForestRegressor(n_estimators=10)
        model.fit(X_train, y_train)
        predictions = model.predict(X_test)
        
        print("  ✅ 基础机器学习功能正常")
        return True
        
    except Exception as e:
        print(f"  ❌ 基础功能测试失败: {e}")
        return False

def generate_report(core_results, optional_results, app_result, db_result, services_results, basic_result):
    """生成测试报告"""
    print("\n" + "="*60)
    print("📋 系统测试报告")
    print("="*60)
    
    # 核心模块统计
    core_passed = sum(core_results.values())
    core_total = len(core_results)
    print(f"\n📦 核心依赖包: {core_passed}/{core_total} 通过")
    
    # 可选模块统计
    optional_passed = sum(optional_results.values())
    optional_total = len(optional_results)
    print(f"📦 可选依赖包: {optional_passed}/{optional_total} 通过")
    
    # 功能测试统计
    function_tests = [
        ("Flask应用创建", app_result),
        ("数据库连接", db_result),
        ("基础功能", basic_result)
    ]
    
    function_passed = sum(result for _, result in function_tests)
    function_total = len(function_tests)
    print(f"🔧 功能测试: {function_passed}/{function_total} 通过")
    
    # 服务测试统计
    services_passed = sum(services_results.values())
    services_total = len(services_results)
    print(f"⚙️ 核心服务: {services_passed}/{services_total} 通过")
    
    # 总体评估
    total_passed = core_passed + function_passed
    total_critical = core_total + function_total
    
    print(f"\n🎯 总体状态: {total_passed}/{total_critical} 关键测试通过")
    
    if total_passed == total_critical:
        print("✅ 系统状态: 优秀 - 所有关键功能正常")
        recommendation = "系统已准备就绪，可以正常使用所有功能。"
    elif total_passed >= total_critical * 0.8:
        print("⚠️ 系统状态: 良好 - 大部分功能正常")
        recommendation = "系统基本可用，建议安装缺失的依赖包以获得完整功能。"
    else:
        print("❌ 系统状态: 需要修复 - 存在关键问题")
        recommendation = "建议使用修复版启动脚本或手动安装核心依赖包。"
    
    print(f"\n💡 建议: {recommendation}")
    
    # 详细建议
    print("\n📋 详细建议:")
    
    if not all(core_results.values()):
        print("  1. 安装缺失的核心依赖包:")
        for name, passed in core_results.items():
            if not passed:
                print(f"     pip install {name.lower()}")
    
    if optional_passed < optional_total:
        print("  2. 安装可选依赖包以获得高级功能:")
        for name, passed in optional_results.items():
            if not passed:
                if name == "XGBoost":
                    print("     pip install xgboost")
                elif name == "LightGBM":
                    print("     pip install lightgbm")
                elif name == "CVXPY":
                    print("     pip install cvxpy")
    
    if not app_result or not db_result:
        print("  3. 如果应用创建或数据库连接失败，尝试:")
        print("     python quick_start_fixed.py")
    
    print("\n🚀 启动建议:")
    if total_passed >= total_critical * 0.8:
        print("  - 运行: python run_system.py")
        print("  - 或运行: python app.py")
    else:
        print("  - 运行: python quick_start_fixed.py")
    
    print("\n📖 更多帮助:")
    print("  - 查看安装指南: INSTALL_GUIDE.md")
    print("  - 查看README: README.md")

def main():
    """主函数"""
    print("多因子选股系统测试")
    print("="*40)
    
    # 运行所有测试
    core_results = test_imports()
    optional_results = test_optional_imports()
    app_result = test_app_creation()
    db_result = test_database_connection()
    services_results = test_services()
    basic_result = test_basic_functionality()
    
    # 生成报告
    generate_report(core_results, optional_results, app_result, db_result, services_results, basic_result)

if __name__ == "__main__":
    main()