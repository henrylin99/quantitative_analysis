#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查机器学习相关表的状态
"""

import pymysql

def check_ml_tables():
    """检查机器学习相关表"""
    connection = pymysql.connect(
        host='localhost',
        user='root', 
        password='Flameaway3.',
        database='stock_cursor',
        charset='utf8mb4'
    )

    try:
        with connection.cursor() as cursor:
            print("🔍 检查机器学习相关表状态")
            print("=" * 60)
            
            # 检查因子相关表是否存在
            cursor.execute('SHOW TABLES LIKE "%factor%"')
            tables = cursor.fetchall()
            print('📊 因子相关表:')
            for table in tables:
                print(f'  ✅ {table[0]}')
            
            print()
            
            # 检查ML相关表是否存在
            cursor.execute('SHOW TABLES LIKE "%ml%"')
            tables = cursor.fetchall()
            print('🤖 ML相关表:')
            for table in tables:
                print(f'  ✅ {table[0]}')
            
            print()
            
            # 检查factor_definition表的数据
            try:
                cursor.execute('SELECT COUNT(*) FROM factor_definition')
                count = cursor.fetchone()[0]
                print(f'📋 factor_definition表记录数: {count}')
                
                if count > 0:
                    cursor.execute('SELECT factor_id, factor_name FROM factor_definition LIMIT 5')
                    factors = cursor.fetchall()
                    print('前5个因子定义:')
                    for factor in factors:
                        print(f'  - {factor[0]}: {factor[1]}')
            except Exception as e:
                print(f'❌ factor_definition表不存在或查询失败: {e}')
            
            print()
            
            # 检查factor_values表的数据
            try:
                cursor.execute('SELECT COUNT(*) FROM factor_values')
                count = cursor.fetchone()[0]
                print(f'📈 factor_values表记录数: {count}')
                
                if count > 0:
                    cursor.execute('SELECT DISTINCT factor_id FROM factor_values LIMIT 10')
                    factors = cursor.fetchall()
                    print('前10个已计算的因子:')
                    for factor in factors:
                        print(f'  - {factor[0]}')
            except Exception as e:
                print(f'❌ factor_values表不存在或查询失败: {e}')
            
            print()
            
            # 检查ml_model_definition表的数据
            try:
                cursor.execute('SELECT COUNT(*) FROM ml_model_definition')
                count = cursor.fetchone()[0]
                print(f'🤖 ml_model_definition表记录数: {count}')
                
                if count > 0:
                    cursor.execute('SELECT model_id, model_name FROM ml_model_definition LIMIT 5')
                    models = cursor.fetchall()
                    print('前5个模型定义:')
                    for model in models:
                        print(f'  - {model[0]}: {model[1]}')
            except Exception as e:
                print(f'❌ ml_model_definition表不存在或查询失败: {e}')
            
            print()
            print("🔧 建议解决方案:")
            print("1. 如果表不存在，需要运行数据库迁移脚本")
            print("2. 如果因子定义为空，需要初始化内置因子")
            print("3. 如果因子值为空，需要计算因子数据")
            print("4. 如果模型定义为空，需要创建演示模型")

    finally:
        connection.close()

if __name__ == "__main__":
    check_ml_tables() 