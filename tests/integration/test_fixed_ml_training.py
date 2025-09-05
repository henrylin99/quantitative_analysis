#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的机器学习训练功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import MLModelDefinition
from app.services.ml_models import MLModelManager
import requests
import json

def test_fixed_ml_training():
    """测试修复后的机器学习训练功能"""
    print("🧪 测试修复后的机器学习训练功能")
    print("=" * 60)
    
    try:
        # 1. 测试通过API训练模型
        print("1️⃣ 测试API训练功能...")
        
        # 准备训练请求
        train_data = {
            'model_id': 'simple_demo_model',
            'start_date': '2023-01-01',
            'end_date': '2023-12-31'
        }
        
        # 发送训练请求
        response = requests.post(
            'http://localhost:5001/api/ml-factor/models/train',
            json=train_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"   API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("   ✅ API训练成功！")
            print(f"   📊 训练指标:")
            if 'metrics' in result:
                for key, value in result['metrics'].items():
                    if isinstance(value, (int, float)):
                        print(f"      {key}: {value:.4f}")
                    elif isinstance(value, dict):
                        print(f"      {key}: {len(value)} 项")
                    else:
                        print(f"      {key}: {value}")
        else:
            print(f"   ❌ API训练失败: {response.text}")
        
        print()
        
        # 2. 测试通过API预测功能
        print("2️⃣ 测试API预测功能...")
        
        predict_data = {
            'model_id': 'simple_demo_model',
            'trade_date': '2025-05-23'
        }
        
        response = requests.post(
            'http://localhost:5001/api/ml-factor/models/predict',
            json=predict_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"   API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("   ✅ API预测成功！")
            if 'predictions' in result:
                predictions = result['predictions']
                print(f"   📊 预测结果: {len(predictions)} 只股票")
                
                # 显示前5名
                if predictions:
                    sorted_predictions = sorted(predictions, key=lambda x: x['predicted_return'], reverse=True)
                    print("   🏆 预测收益率前5名:")
                    for i, pred in enumerate(sorted_predictions[:5]):
                        print(f"      {i+1}. {pred['ts_code']}: {pred['predicted_return']:+.4f}")
        else:
            print(f"   ❌ API预测失败: {response.text}")
        
        print()
        
        # 3. 测试直接调用服务
        print("3️⃣ 测试直接调用服务...")
        
        app = create_app()
        with app.app_context():
            ml_manager = MLModelManager()
            
            # 测试训练
            print("   🚀 测试直接训练...")
            result = ml_manager.train_model('simple_demo_model', '2023-01-01', '2023-12-31')
            
            if result['success']:
                print("   ✅ 直接训练成功！")
                print(f"   📊 R²分数: {result['metrics']['test_r2']:.4f}")
            else:
                print(f"   ❌ 直接训练失败: {result['error']}")
            
            # 测试预测
            print("   🔮 测试直接预测...")
            predictions = ml_manager.predict('simple_demo_model', '2025-05-23')
            
            if not predictions.empty:
                print(f"   ✅ 直接预测成功！预测了 {len(predictions)} 只股票")
                top_5 = predictions.nlargest(5, 'predicted_return')
                print("   🏆 预测收益率前5名:")
                for i, (_, row) in enumerate(top_5.iterrows()):
                    print(f"      {i+1}. {row['ts_code']}: {row['predicted_return']:+.4f}")
            else:
                print("   ❌ 直接预测失败")
        
        print("\n🎉 测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fixed_ml_training() 