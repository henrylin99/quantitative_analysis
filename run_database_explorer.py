#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库探索工具运行脚本
快速测试数据库连接和基本功能
"""

from database_explorer import DatabaseExplorer, CustomFactorGenerator
from advanced_factor_library import AdvancedFactorLibrary

def test_database_connection():
    """测试数据库连接"""
    print("🔍 测试数据库连接...")
    
    db_explorer = DatabaseExplorer()
    
    if db_explorer.connect():
        print("✅ 数据库连接成功!")
        
        # 显示表列表
        tables = db_explorer.show_tables()
        
        if tables:
            print(f"\n📊 发现 {len(tables)} 个数据表")
            
            # 查看几个重要表的基本信息
            important_tables = ['stock_basic', 'stock_daily_history', 'stock_factor']
            
            for table in important_tables[:2]:  # 只查看前2个表避免输出过多
                if table in tables:
                    print(f"\n{'='*50}")
                    print(f"📋 表: {table}")
                    print(f"{'='*50}")
                    
                    # 获取表统计信息
                    stats = db_explorer.get_table_stats(table)
                    
                    # 获取样本数据
                    sample = db_explorer.get_table_sample(table, 2)
        
        db_explorer.close()
        return True
    else:
        print("❌ 数据库连接失败!")
        return False

def test_basic_factors():
    """测试基本因子计算"""
    print("\n🧮 测试基本因子计算...")
    
    db_explorer = DatabaseExplorer()
    
    if not db_explorer.connect():
        return False
    
    try:
        factor_generator = CustomFactorGenerator(db_explorer)
        
        # 测试参数
        test_stock = "000001.SZ"
        start_date = "2023-12-01"
        end_date = "2023-12-31"
        
        print(f"📊 测试股票: {test_stock}")
        print(f"📅 测试时间: {start_date} 至 {end_date}")
        
        # 计算动量因子
        momentum_data = factor_generator.calculate_price_momentum_factors(
            ts_code=test_stock,
            start_date=start_date,
            end_date=end_date
        )
        
        if momentum_data is not None and not momentum_data.empty:
            print(f"\n✅ 动量因子计算成功，共 {len(momentum_data)} 条数据")
            print("\n📊 动量因子样本数据:")
            print(momentum_data[['ts_code', 'trade_date', 'momentum_5d', 'momentum_20d']].tail(3))
        
        return True
        
    except Exception as e:
        print(f"❌ 因子计算测试失败: {e}")
        return False
    finally:
        db_explorer.close()

def test_advanced_factors():
    """测试高级因子计算"""
    print("\n🎯 测试高级因子计算...")
    
    try:
        factor_lib = AdvancedFactorLibrary()
        
        # 测试参数
        test_stock = "000001.SZ"
        start_date = "2023-12-01"
        end_date = "2023-12-31"
        
        print(f"📊 测试股票: {test_stock}")
        print(f"📅 测试时间: {start_date} 至 {end_date}")
        
        # 测试Alpha因子计算
        alpha_data = factor_lib.calculate_alpha_factors(
            ts_code=test_stock,
            start_date=start_date,
            end_date=end_date
        )
        
        if alpha_data is not None and not alpha_data.empty:
            print(f"\n✅ Alpha因子计算成功，共 {len(alpha_data)} 条数据")
            print("\n📊 Alpha因子样本数据:")
            print(alpha_data[['ts_code', 'trade_date', 'alpha001', 'alpha002', 'alpha003']].tail(3))
        
        factor_lib.close()
        return True
        
    except Exception as e:
        print(f"❌ 高级因子计算测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 数据库探索工具测试")
    print("=" * 60)
    
    # 测试数据库连接
    if not test_database_connection():
        print("❌ 数据库连接测试失败，请检查数据库配置")
        return
    
    # 测试基本因子计算
    if test_basic_factors():
        print("\n✅ 基本因子计算测试通过")
    else:
        print("\n❌ 基本因子计算测试失败")
    
    # 测试高级因子计算
    if test_advanced_factors():
        print("\n✅ 高级因子计算测试通过")
    else:
        print("\n❌ 高级因子计算测试失败")
    
    print("\n🎉 测试完成!")
    print("\n💡 下一步:")
    print("1. 运行 python database_explorer.py 进行完整的数据库探索")
    print("2. 运行 python advanced_factor_library.py 进行高级因子计算")
    print("3. 根据需要修改股票代码和时间范围进行自定义分析")

if __name__ == "__main__":
    main() 