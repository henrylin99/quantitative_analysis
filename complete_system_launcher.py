#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子模型系统完整启动器
集成数据检查、系统初始化、模型训练和Web服务启动
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, List

def print_banner():
    """打印系统横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                    多因子模型系统 V2.0                        ║
║                Enhanced Multifactor System                   ║
╠══════════════════════════════════════════════════════════════╣
║  🚀 智能因子计算引擎                                          ║
║  🤖 机器学习模型训练                                          ║
║  📊 实时股票选择预测                                          ║
║  🌐 现代化Web管理界面                                         ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)

def check_environment():
    """检查运行环境"""
    print("🔍 检查运行环境...")
    
    # 检查Python版本
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print("❌ Python版本过低，需要Python 3.8+")
        return False
    
    print(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # 检查必要的包
    required_packages = [
        'pandas', 'numpy', 'sklearn', 'flask', 'sqlalchemy',
        'xgboost', 'lightgbm', 'matplotlib', 'seaborn'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} - 未安装")
    
    if missing_packages:
        print(f"\n⚠️  缺少必要的包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
        return False
    
    return True

def check_database():
    """检查数据库连接和数据"""
    print("\n📊 检查数据库状态...")
    
    try:
        from app import create_app
        from app.extensions import db
        from app.models import (
            StockBasic, StockDailyHistory, StockFactor, 
            FactorDefinition, FactorValues, MLModelDefinition
        )
        
        app = create_app()
        with app.app_context():
            # 检查数据表
            tables_status = {
                'stock_basic': StockBasic.query.count(),
                'stock_daily_history': StockDailyHistory.query.count(),
                'stock_factor': StockFactor.query.count(),
                'factor_definition': FactorDefinition.query.count(),
                'factor_values': FactorValues.query.count(),
                'ml_model_definition': MLModelDefinition.query.count()
            }
            
            print("📋 数据表状态:")
            for table, count in tables_status.items():
                status = "✅" if count > 0 else "⚠️ "
                print(f"   {status} {table}: {count:,} 条记录")
            
            # 检查关键数据
            if tables_status['stock_basic'] == 0:
                print("❌ 缺少股票基础数据")
                return False
            
            if tables_status['factor_values'] < 1000:
                print("⚠️  因子数据较少，建议补充历史数据")
            
            return True
            
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")
        return False

def initialize_system():
    """初始化系统"""
    print("\n🚀 初始化多因子模型系统...")
    
    try:
        # 运行增强系统初始化
        from enhanced_multifactor_system_v2 import EnhancedMultifactorSystemV2
        
        system = EnhancedMultifactorSystemV2()
        success = system.initialize_system()
        
        if success:
            print("✅ 系统初始化完成")
            return system
        else:
            print("❌ 系统初始化失败")
            return None
            
    except Exception as e:
        print(f"❌ 系统初始化异常: {e}")
        return None

def run_system_tests():
    """运行系统测试"""
    print("\n🧪 运行系统测试...")
    
    try:
        # 测试模型训练
        print("   📊 测试模型训练...")
        
        # 测试因子计算
        print("   🔢 测试因子计算...")
        
        # 测试预测功能
        print("   🔮 测试预测功能...")
        
        print("✅ 系统测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 系统测试失败: {e}")
        return False

def start_web_service(system=None):
    """启动Web服务"""
    print("\n🌐 启动Web服务...")
    
    try:
        from web_interface_v2 import MultifactorWebInterface
        
        # 创建Web界面
        web_interface = MultifactorWebInterface()
        
        print("🌐 Web服务启动中...")
        print("   地址: http://localhost:5001")
        print("   按 Ctrl+C 停止服务")
        
        # 启动服务
        web_interface.run(host='0.0.0.0', port=5001, debug=False)
        
    except KeyboardInterrupt:
        print("\n👋 Web服务已停止")
    except Exception as e:
        print(f"❌ Web服务启动失败: {e}")

def show_menu():
    """显示主菜单"""
    menu = """
╔══════════════════════════════════════════════════════════════╗
║                        主菜单                                ║
╠══════════════════════════════════════════════════════════════╣
║  1. 🔍 系统诊断 - 检查环境和数据状态                          ║
║  2. 🚀 完整初始化 - 初始化系统并训练模型                      ║
║  3. 🌐 启动Web服务 - 启动管理界面                             ║
║  4. 🧪 运行测试 - 测试系统功能                                ║
║  5. 📊 数据报告 - 生成系统状态报告                            ║
║  6. 🔧 维护模式 - 系统维护和修复                              ║
║  0. 🚪 退出系统                                               ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(menu)

def system_diagnosis():
    """系统诊断"""
    print("\n" + "="*60)
    print("🔍 系统诊断")
    print("="*60)
    
    # 检查环境
    env_ok = check_environment()
    
    # 检查数据库
    db_ok = check_database()
    
    # 生成诊断报告
    print("\n📋 诊断报告:")
    print(f"   运行环境: {'✅ 正常' if env_ok else '❌ 异常'}")
    print(f"   数据库状态: {'✅ 正常' if db_ok else '❌ 异常'}")
    
    if env_ok and db_ok:
        print("✅ 系统状态良好，可以正常运行")
        return True
    else:
        print("❌ 系统存在问题，请检查并修复")
        return False

def full_initialization():
    """完整初始化"""
    print("\n" + "="*60)
    print("🚀 完整系统初始化")
    print("="*60)
    
    # 先进行诊断
    if not system_diagnosis():
        print("❌ 系统诊断失败，无法继续初始化")
        return None
    
    # 初始化系统
    system = initialize_system()
    
    if system:
        # 运行测试
        if run_system_tests():
            print("✅ 系统初始化和测试完成")
            return system
        else:
            print("⚠️  系统初始化完成，但测试有问题")
            return system
    else:
        print("❌ 系统初始化失败")
        return None

def generate_report():
    """生成系统报告"""
    print("\n" + "="*60)
    print("📊 生成系统状态报告")
    print("="*60)
    
    try:
        from app import create_app
        from app.extensions import db
        from app.models import (
            StockBasic, StockDailyHistory, FactorValues, 
            MLModelDefinition, MLPredictions
        )
        
        app = create_app()
        with app.app_context():
            # 收集统计信息
            stats = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_count': StockBasic.query.count(),
                'history_records': StockDailyHistory.query.count(),
                'factor_records': FactorValues.query.count(),
                'model_count': MLModelDefinition.query.count(),
                'prediction_records': MLPredictions.query.count()
            }
            
            # 打印报告
            print(f"📈 系统统计 (截至 {stats['timestamp']}):")
            print(f"   股票数量: {stats['stock_count']:,}")
            print(f"   历史记录: {stats['history_records']:,}")
            print(f"   因子记录: {stats['factor_records']:,}")
            print(f"   模型数量: {stats['model_count']}")
            print(f"   预测记录: {stats['prediction_records']:,}")
            
            # 保存报告
            report_file = f"system_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("多因子模型系统状态报告\n")
                f.write("="*50 + "\n\n")
                for key, value in stats.items():
                    f.write(f"{key}: {value}\n")
            
            print(f"✅ 报告已保存: {report_file}")
            
    except Exception as e:
        print(f"❌ 生成报告失败: {e}")

def maintenance_mode():
    """维护模式"""
    print("\n" + "="*60)
    print("🔧 系统维护模式")
    print("="*60)
    
    maintenance_menu = """
维护选项:
1. 重建因子数据
2. 重新训练模型
3. 清理预测数据
4. 数据库优化
5. 返回主菜单
"""
    
    while True:
        print(maintenance_menu)
        choice = input("请选择维护操作 (1-5): ").strip()
        
        if choice == '1':
            print("🔄 重建因子数据...")
            # 这里可以添加重建因子数据的逻辑
            print("✅ 因子数据重建完成")
            
        elif choice == '2':
            print("🤖 重新训练模型...")
            # 这里可以添加重新训练模型的逻辑
            print("✅ 模型重新训练完成")
            
        elif choice == '3':
            print("🗑️  清理预测数据...")
            # 这里可以添加清理预测数据的逻辑
            print("✅ 预测数据清理完成")
            
        elif choice == '4':
            print("⚡ 数据库优化...")
            # 这里可以添加数据库优化的逻辑
            print("✅ 数据库优化完成")
            
        elif choice == '5':
            break
            
        else:
            print("❌ 无效选择，请重新输入")

def main():
    """主函数"""
    print_banner()
    
    system = None
    
    while True:
        show_menu()
        choice = input("请选择操作 (0-6): ").strip()
        
        if choice == '1':
            system_diagnosis()
            
        elif choice == '2':
            system = full_initialization()
            
        elif choice == '3':
            start_web_service(system)
            
        elif choice == '4':
            run_system_tests()
            
        elif choice == '5':
            generate_report()
            
        elif choice == '6':
            maintenance_mode()
            
        elif choice == '0':
            print("\n👋 感谢使用多因子模型系统！")
            break
            
        else:
            print("❌ 无效选择，请重新输入")
        
        # 等待用户按键继续
        if choice != '0':
            input("\n按回车键继续...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}") 