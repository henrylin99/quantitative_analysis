#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用Flask应用上下文检查机器学习相关表的状态
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorDefinition, FactorValues, MLModelDefinition
from sqlalchemy import text

def check_ml_tables():
    """检查机器学习相关表"""
    app = create_app()
    
    with app.app_context():
        print("🔍 检查机器学习相关表状态")
        print("=" * 60)
        
        try:
            # 检查因子相关表是否存在
            result = db.session.execute(text('SHOW TABLES LIKE "%factor%"'))
            tables = result.fetchall()
            print('📊 因子相关表:')
            for table in tables:
                print(f'  ✅ {table[0]}')
            
            print()
            
            # 检查ML相关表是否存在
            result = db.session.execute(text('SHOW TABLES LIKE "%ml%"'))
            tables = result.fetchall()
            print('🤖 ML相关表:')
            for table in tables:
                print(f'  ✅ {table[0]}')
            
            print()
            
            # 检查factor_definition表的数据
            try:
                count = FactorDefinition.query.count()
                print(f'📋 factor_definition表记录数: {count}')
                
                if count > 0:
                    factors = FactorDefinition.query.limit(5).all()
                    print('前5个因子定义:')
                    for factor in factors:
                        print(f'  - {factor.factor_id}: {factor.factor_name}')
            except Exception as e:
                print(f'❌ factor_definition表查询失败: {e}')
            
            print()
            
            # 检查factor_values表的数据
            try:
                count = FactorValues.query.count()
                print(f'📈 factor_values表记录数: {count}')
                
                if count > 0:
                    result = db.session.execute(text('SELECT DISTINCT factor_id FROM factor_values LIMIT 10'))
                    factors = result.fetchall()
                    print('前10个已计算的因子:')
                    for factor in factors:
                        print(f'  - {factor[0]}')
            except Exception as e:
                print(f'❌ factor_values表查询失败: {e}')
            
            print()
            
            # 检查ml_model_definition表的数据
            try:
                count = MLModelDefinition.query.count()
                print(f'🤖 ml_model_definition表记录数: {count}')
                
                if count > 0:
                    models = MLModelDefinition.query.limit(5).all()
                    print('前5个模型定义:')
                    for model in models:
                        print(f'  - {model.model_id}: {model.model_name}')
            except Exception as e:
                print(f'❌ ml_model_definition表查询失败: {e}')
            
            print()
            print("🔧 建议解决方案:")
            
            # 检查具体缺失的内容
            factor_def_count = 0
            factor_val_count = 0
            model_def_count = 0
            
            try:
                factor_def_count = FactorDefinition.query.count()
            except:
                pass
                
            try:
                factor_val_count = FactorValues.query.count()
            except:
                pass
                
            try:
                model_def_count = MLModelDefinition.query.count()
            except:
                pass
            
            if factor_def_count == 0:
                print("1. ❌ 需要初始化因子定义 - 运行: python init_ml_factor_system.py")
            else:
                print("1. ✅ 因子定义已存在")
                
            if factor_val_count == 0:
                print("2. ❌ 需要计算因子数据 - 这需要历史价格数据")
            else:
                print("2. ✅ 因子数据已存在")
                
            if model_def_count == 0:
                print("3. ❌ 需要创建模型定义 - 可以通过Web界面或API创建")
            else:
                print("3. ✅ 模型定义已存在")
                
            print("4. 💡 如果要快速测试，建议使用独立的演示模型（如final_demo_ml_model.py）")
            
        except Exception as e:
            print(f"❌ 检查过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    check_ml_tables() 