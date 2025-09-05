#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用实际可用的日期范围测试机器学习训练
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorValues, MLModelDefinition
from app.services.ml_models import MLModelManager
from sqlalchemy import text

def test_ml_training_with_real_dates():
    """使用实际日期测试机器学习训练"""
    app = create_app()
    
    with app.app_context():
        print("🧪 使用实际日期测试机器学习训练")
        print("=" * 60)
        
        try:
            # 1. 获取实际的日期范围
            result = db.session.execute(text('''
                SELECT 
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date
                FROM factor_values
            '''))
            
            date_range = result.fetchone()
            min_date, max_date = date_range
            
            print(f"📅 实际数据日期范围: {min_date} 至 {max_date}")
            
            # 2. 获取可用的模型
            models = MLModelDefinition.query.all()
            print(f"🤖 找到 {len(models)} 个模型")
            
            # 使用第二个模型（working_demo_model），因为它有2个因子
            if len(models) >= 2:
                model = models[1]  # working_demo_model
            else:
                model = models[0]
                
            print(f"🎯 测试模型: {model.model_id} - {model.model_name}")
            print(f"📋 使用因子: {model.factor_list}")
            
            # 3. 创建ML管理器并尝试训练
            ml_manager = MLModelManager()
            
            print(f"\n🚀 开始训练模型...")
            print(f"   训练日期范围: {min_date} 至 {max_date}")
            
            # 由于只有一天的数据，我们需要特殊处理
            # 先检查是否有足够的数据进行训练
            factor_query = FactorValues.query.filter(
                FactorValues.factor_id.in_(model.factor_list),
                FactorValues.trade_date >= min_date,
                FactorValues.trade_date <= max_date
            )
            
            factor_count = factor_query.count()
            print(f"📊 可用因子数据: {factor_count} 条记录")
            
            if factor_count < 100:
                print("⚠️  数据量太少，无法进行有效的机器学习训练")
                print("💡 建议:")
                print("   1. 计算更多历史日期的因子数据")
                print("   2. 或者使用演示模型（final_demo_ml_model.py）")
                return
            
            # 尝试训练
            result = ml_manager.train_model(model.model_id, str(min_date), str(max_date))
            
            if result['success']:
                print("✅ 模型训练成功！")
                print("📊 训练指标:")
                for key, value in result['metrics'].items():
                    if isinstance(value, (int, float)):
                        print(f"   {key}: {value:.4f}")
                    else:
                        print(f"   {key}: {value}")
            else:
                print(f"❌ 模型训练失败: {result['error']}")
                
                # 提供详细的错误分析
                print("\n🔍 错误分析:")
                if "训练数据为空" in result['error']:
                    print("   原因: 数据准备阶段失败")
                    print("   可能的问题:")
                    print("   1. 因子数据和价格数据日期不匹配")
                    print("   2. 目标变量计算失败")
                    print("   3. 数据清洗后为空")
                
        except Exception as e:
            print(f"❌ 测试过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_ml_training_with_real_dates() 