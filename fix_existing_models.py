#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复现有模型，使其只使用有数据的因子
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorDefinition, FactorValues, MLModelDefinition
from sqlalchemy import text

def fix_existing_models():
    """修复现有模型"""
    app = create_app()
    
    with app.app_context():
        print("🔧 修复现有模型")
        print("=" * 60)
        
        try:
            # 1. 找出所有有数据的因子
            result = db.session.execute(text('''
                SELECT DISTINCT factor_id, COUNT(*) as count
                FROM factor_values 
                GROUP BY factor_id 
                ORDER BY count DESC
            '''))
            
            available_factors = result.fetchall()
            print("📊 可用的因子数据:")
            for factor_id, count in available_factors:
                print(f"   ✅ {factor_id}: {count} 条记录")
            
            if not available_factors:
                print("❌ 没有可用的因子数据")
                return
            
            # 2. 获取所有模型
            models = MLModelDefinition.query.all()
            print(f"\n🤖 找到 {len(models)} 个模型需要修复")
            
            for model in models:
                print(f"\n🔧 修复模型: {model.model_id} - {model.model_name}")
                print(f"   原因子列表: {model.factor_list}")
                
                # 检查哪些因子有数据
                available_model_factors = []
                for factor_id in model.factor_list:
                    factor_count = FactorValues.query.filter_by(factor_id=factor_id).count()
                    if factor_count > 0:
                        available_model_factors.append(factor_id)
                        print(f"   ✅ {factor_id}: {factor_count} 条记录")
                    else:
                        print(f"   ❌ {factor_id}: 无数据")
                
                if not available_model_factors:
                    print("   ⚠️  该模型没有可用因子，使用所有可用因子")
                    # 使用所有可用因子
                    available_model_factors = [factor[0] for factor in available_factors]
                
                # 更新模型的因子列表
                old_factors = model.factor_list.copy()
                model.factor_list = available_model_factors
                
                print(f"   🔄 更新因子列表:")
                print(f"      旧: {old_factors}")
                print(f"      新: {available_model_factors}")
                
                # 保存更改
                db.session.commit()
                print(f"   ✅ 模型 {model.model_id} 修复完成")
            
            print(f"\n🎉 所有模型修复完成！")
            print("现在可以尝试训练模型了")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ 修复过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    fix_existing_models() 