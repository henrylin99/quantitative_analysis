#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复working_demo_model，改为使用模拟目标变量
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import MLModelDefinition

def fix_working_demo_model():
    """修复working_demo_model，改为使用模拟目标变量"""
    app = create_app()
    
    with app.app_context():
        print("🔧 修复working_demo_model")
        print("=" * 50)
        
        try:
            # 查找模型
            model = MLModelDefinition.query.filter_by(model_id='working_demo_model').first()
            if not model:
                print("❌ 未找到working_demo_model")
                return
            
            print(f"📋 当前配置:")
            print(f"   目标类型: {model.target_type}")
            print(f"   因子列表: {model.factor_list}")
            
            # 修改目标类型为模拟数据
            model.target_type = 'simulated_return'
            
            # 提交更改
            db.session.commit()
            
            print(f"\n✅ 修复完成!")
            print(f"   新目标类型: {model.target_type}")
            print(f"   现在可以使用模拟目标变量进行训练")
            
            # 测试训练
            print(f"\n🧪 测试训练...")
            from app.services.ml_models import MLModelManager
            
            ml_manager = MLModelManager()
            result = ml_manager.train_model('working_demo_model', '2023-01-01', '2023-12-31')
            
            if result['success']:
                print(f"   ✅ 训练成功!")
                print(f"   📊 测试R²: {result['metrics']['test_r2']:.4f}")
                print(f"   📊 样本数量: {result['metrics']['sample_count']}")
                print(f"   📊 特征数量: {result['metrics']['feature_count']}")
            else:
                print(f"   ❌ 训练失败: {result['error']}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ 修复过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    fix_working_demo_model() 