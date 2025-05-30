#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查模型需要的因子和实际可用的因子数据
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorDefinition, FactorValues, MLModelDefinition
from sqlalchemy import text

def check_model_factors():
    """检查模型因子匹配情况"""
    app = create_app()
    
    with app.app_context():
        print("🔍 检查模型因子匹配情况")
        print("=" * 60)
        
        try:
            # 获取所有模型定义
            models = MLModelDefinition.query.all()
            print(f"📊 找到 {len(models)} 个模型定义")
            
            for model in models:
                print(f"\n🤖 模型: {model.model_id} - {model.model_name}")
                print(f"   类型: {model.model_type}")
                print(f"   目标: {model.target_type}")
                print(f"   需要的因子: {model.factor_list}")
                
                # 检查每个因子的数据可用性
                missing_factors = []
                available_factors = []
                
                for factor_id in model.factor_list:
                    # 检查因子定义是否存在
                    factor_def = FactorDefinition.query.filter_by(factor_id=factor_id).first()
                    if not factor_def:
                        print(f"   ❌ 因子定义不存在: {factor_id}")
                        missing_factors.append(factor_id)
                        continue
                    
                    # 检查因子数据是否存在
                    factor_data_count = FactorValues.query.filter_by(factor_id=factor_id).count()
                    if factor_data_count == 0:
                        print(f"   ❌ 因子数据为空: {factor_id} ({factor_def.factor_name})")
                        missing_factors.append(factor_id)
                    else:
                        print(f"   ✅ 因子数据可用: {factor_id} ({factor_def.factor_name}) - {factor_data_count} 条记录")
                        available_factors.append(factor_id)
                
                print(f"\n   📈 可用因子: {len(available_factors)}/{len(model.factor_list)}")
                print(f"   ❌ 缺失因子: {missing_factors}")
                
                if len(available_factors) < len(model.factor_list):
                    print(f"   ⚠️  模型无法训练 - 缺少必要的因子数据")
                else:
                    print(f"   ✅ 模型可以训练")
            
            print(f"\n📋 所有可用的因子数据:")
            result = db.session.execute(text('''
                SELECT factor_id, COUNT(*) as count, 
                       MIN(trade_date) as min_date, 
                       MAX(trade_date) as max_date
                FROM factor_values 
                GROUP BY factor_id 
                ORDER BY factor_id
            '''))
            
            available_factor_data = result.fetchall()
            for row in available_factor_data:
                factor_id, count, min_date, max_date = row
                print(f"   📊 {factor_id}: {count} 条记录 ({min_date} 至 {max_date})")
            
            print(f"\n🔧 解决方案:")
            print("1. 如果要使用现有模型，需要计算缺失的因子数据")
            print("2. 或者创建一个只使用可用因子的新模型")
            print("3. 或者使用独立的演示模型（推荐）")
            
            # 建议创建一个使用可用因子的模型
            if available_factor_data:
                available_factor_ids = [row[0] for row in available_factor_data]
                print(f"\n💡 建议创建模型使用这些可用因子:")
                print(f"   {available_factor_ids}")
                
        except Exception as e:
            print(f"❌ 检查过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    check_model_factors() 