#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建一个使用现有可用因子的工作模型
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import MLModelDefinition

def create_working_model():
    """创建使用可用因子的工作模型"""
    app = create_app()
    
    with app.app_context():
        print("🔧 创建使用可用因子的工作模型")
        print("=" * 60)
        
        try:
            # 检查模型是否已存在
            existing_model = MLModelDefinition.query.filter_by(model_id='working_demo_model').first()
            if existing_model:
                print("⚠️  模型已存在，删除旧模型...")
                db.session.delete(existing_model)
                db.session.commit()
            
            # 创建新模型定义
            model_def = MLModelDefinition(
                model_id='working_demo_model',
                model_name='可用因子演示模型',
                model_type='random_forest',
                factor_list=['chip_concentration', 'money_flow_strength'],  # 使用可用的因子
                target_type='return_5d',
                model_params={
                    'n_estimators': 100,
                    'max_depth': 10,
                    'random_state': 42
                },
                training_config={
                    'test_size': 0.2,
                    'validation_method': 'time_series_split',
                    'cv_folds': 5,
                    'feature_selection': False,  # 因子太少，不做特征选择
                    'scaling_method': 'robust'
                }
            )
            
            db.session.add(model_def)
            db.session.commit()
            
            print("✅ 成功创建工作模型:")
            print(f"   模型ID: {model_def.model_id}")
            print(f"   模型名称: {model_def.model_name}")
            print(f"   使用因子: {model_def.factor_list}")
            print(f"   预测目标: {model_def.target_type}")
            
            print("\n🎯 现在可以尝试训练这个模型了！")
            print("   在Web界面中选择 'working_demo_model' 进行训练")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ 创建模型失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    create_working_model() 