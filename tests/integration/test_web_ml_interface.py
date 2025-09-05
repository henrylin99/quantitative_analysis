#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Web界面的机器学习功能
"""

import requests
import json
import time

def test_web_ml_interface():
    """测试Web界面的机器学习功能"""
    print("🌐 测试Web界面机器学习功能")
    print("=" * 60)
    
    base_url = "http://localhost:5001"
    
    try:
        # 1. 测试获取模型列表
        print("1️⃣ 测试获取模型列表...")
        response = requests.get(f"{base_url}/api/ml-factor/models/list")
        
        if response.status_code == 200:
            models = response.json()
            print(f"   ✅ 成功获取 {len(models)} 个模型")
            print(f"   📋 模型列表: {models}")
            if isinstance(models, list) and models:
                for model in models:
                    if isinstance(model, dict):
                        print(f"      - {model.get('model_id', 'N/A')}: {model.get('model_name', 'N/A')} ({model.get('target_type', 'N/A')})")
                    else:
                        print(f"      - {model}")
            else:
                print("   ⚠️  模型列表格式异常")
        else:
            print(f"   ❌ 获取模型列表失败: {response.status_code}")
            return
        
        print()
        
        # 2. 测试训练working_demo_model
        print("2️⃣ 测试训练working_demo_model...")
        train_data = {
            'model_id': 'working_demo_model',
            'start_date': '2023-01-01',
            'end_date': '2024-01-01'
        }
        
        response = requests.post(
            f"{base_url}/api/ml-factor/models/train",
            json=train_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("   ✅ 训练成功!")
            if 'metrics' in result:
                print(f"      测试R²: {result['metrics'].get('test_r2', 'N/A'):.4f}")
                print(f"      样本数量: {result['metrics'].get('sample_count', 'N/A')}")
                print(f"      特征数量: {result['metrics'].get('feature_count', 'N/A')}")
        else:
            print(f"   ❌ 训练失败: {response.status_code}")
            print(f"      错误信息: {response.text}")
            return
        
        print()
        
        # 3. 测试预测功能
        print("3️⃣ 测试预测功能...")
        predict_data = {
            'model_id': 'working_demo_model',
            'trade_date': '2025-05-23'
        }
        
        response = requests.post(
            f"{base_url}/api/ml-factor/models/predict",
            json=predict_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("   ✅ 预测成功!")
            if 'predictions' in result:
                predictions = result['predictions']
                print(f"      预测股票数量: {len(predictions)}")
                
                # 显示前5名
                if predictions:
                    sorted_predictions = sorted(predictions, key=lambda x: x['predicted_return'], reverse=True)
                    print("      🏆 预测收益率前5名:")
                    for i, pred in enumerate(sorted_predictions[:5]):
                        print(f"         {i+1}. {pred['ts_code']}: {pred['predicted_return']:+.4f}")
        else:
            print(f"   ❌ 预测失败: {response.status_code}")
            print(f"      错误信息: {response.text}")
            return
        
        print()
        
        # 4. 测试simple_demo_model
        print("4️⃣ 测试simple_demo_model...")
        
        # 训练
        train_data['model_id'] = 'simple_demo_model'
        response = requests.post(
            f"{base_url}/api/ml-factor/models/train",
            json=train_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            print("   ✅ simple_demo_model训练成功!")
        else:
            print(f"   ❌ simple_demo_model训练失败: {response.status_code}")
        
        # 预测
        predict_data['model_id'] = 'simple_demo_model'
        response = requests.post(
            f"{base_url}/api/ml-factor/models/predict",
            json=predict_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            print("   ✅ simple_demo_model预测成功!")
        else:
            print(f"   ❌ simple_demo_model预测失败: {response.status_code}")
        
        print()
        print("🎉 Web界面机器学习功能测试完成!")
        print("💡 现在您可以在Web界面中正常使用『模型管理』功能了")
        print("   - working_demo_model: 使用真实因子数据 + 模拟目标变量")
        print("   - simple_demo_model: 使用真实因子数据 + 模拟目标变量")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_web_ml_interface() 