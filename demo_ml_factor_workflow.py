#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多因子模型系统演示脚本
展示完整的工作流程：因子计算 -> 模型创建 -> 训练 -> 预测 -> 股票评分 -> 投资组合
"""

import requests
import json
import time
from datetime import datetime, timedelta

# API基础URL
BASE_URL = "http://127.0.0.1:5001/api/ml-factor"

def print_step(step_name):
    """打印步骤标题"""
    print(f"\n{'='*60}")
    print(f"步骤: {step_name}")
    print(f"{'='*60}")

def print_result(result):
    """打印结果"""
    print(json.dumps(result, indent=2, ensure_ascii=False))

def demo_factor_calculation():
    """演示因子计算"""
    print_step("1. 计算因子值")
    
    # 获取当前日期
    trade_date = datetime.now().strftime('%Y-%m-%d')
    
    # 计算所有因子
    response = requests.post(f"{BASE_URL}/factors/calculate", json={
        "trade_date": trade_date,
        "factor_ids": [],  # 空数组表示计算所有因子
        "ts_codes": []     # 空数组表示计算所有股票
    })
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 因子计算完成")
        print_result(result)
        return True
    else:
        print(f"❌ 因子计算失败: {response.text}")
        return False

def demo_model_creation():
    """演示模型创建"""
    print_step("2. 创建机器学习模型")
    
    # 创建一个随机森林模型
    model_config = {
        "model_id": "demo_rf_model",
        "model_name": "演示随机森林模型",
        "model_type": "random_forest",
        "factor_list": ["momentum_5d", "pe_percentile", "money_flow_strength"],
        "target_type": "return_5d",
        "model_params": {
            "n_estimators": 100,
            "max_depth": 10,
            "random_state": 42
        },
        "training_config": {
            "test_size": 0.2,
            "validation_split": 0.2
        }
    }
    
    response = requests.post(f"{BASE_URL}/models/create", json=model_config)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 模型创建成功")
        print_result(result)
        return True
    else:
        print(f"❌ 模型创建失败: {response.text}")
        return False

def demo_model_training():
    """演示模型训练"""
    print_step("3. 训练机器学习模型")
    
    # 训练模型
    training_config = {
        "model_id": "demo_rf_model",
        "start_date": "2023-01-01",
        "end_date": "2024-01-01"
    }
    
    response = requests.post(f"{BASE_URL}/models/train", json=training_config)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 模型训练完成")
        print_result(result)
        return True
    else:
        print(f"❌ 模型训练失败: {response.text}")
        return False

def demo_factor_based_scoring():
    """演示基于因子的股票评分"""
    print_step("4. 基于因子的股票评分")
    
    trade_date = datetime.now().strftime('%Y-%m-%d')
    
    scoring_config = {
        "trade_date": trade_date,
        "factor_list": ["momentum_5d", "pe_percentile", "money_flow_strength"],
        "weights": {
            "momentum_5d": 0.4,
            "pe_percentile": 0.3,
            "money_flow_strength": 0.3
        },
        "method": "factor_weight",
        "top_n": 20
    }
    
    response = requests.post(f"{BASE_URL}/scoring/factor-based", json=scoring_config)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 基于因子的评分完成")
        print_result(result)
        return result.get('top_stocks', [])
    else:
        print(f"❌ 基于因子的评分失败: {response.text}")
        return []

def demo_ml_based_scoring():
    """演示基于ML模型的股票评分"""
    print_step("5. 基于ML模型的股票评分")
    
    trade_date = datetime.now().strftime('%Y-%m-%d')
    
    scoring_config = {
        "trade_date": trade_date,
        "model_ids": ["demo_rf_model"],
        "top_n": 20,
        "ensemble_method": "average"
    }
    
    response = requests.post(f"{BASE_URL}/scoring/ml-based", json=scoring_config)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 基于ML模型的评分完成")
        print_result(result)
        return result.get('top_stocks', [])
    else:
        print(f"❌ 基于ML模型的评分失败: {response.text}")
        return []

def demo_portfolio_optimization():
    """演示投资组合优化"""
    print_step("6. 投资组合优化")
    
    trade_date = datetime.now().strftime('%Y-%m-%d')
    
    portfolio_config = {
        "trade_date": trade_date,
        "selection_method": "factor_based",
        "factor_list": ["momentum_5d", "pe_percentile", "money_flow_strength"],
        "weights": {
            "momentum_5d": 0.4,
            "pe_percentile": 0.3,
            "money_flow_strength": 0.3
        },
        "top_n": 20,
        "optimization_method": "mean_variance",
        "constraints": {
            "max_weight": 0.1,
            "min_weight": 0.01
        }
    }
    
    response = requests.post(f"{BASE_URL}/portfolio/integrated-selection", json=portfolio_config)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 投资组合优化完成")
        print_result(result)
        return True
    else:
        print(f"❌ 投资组合优化失败: {response.text}")
        return False

def demo_batch_workflow():
    """演示批量工作流程"""
    print_step("7. 批量计算因子并评分")
    
    trade_date = datetime.now().strftime('%Y-%m-%d')
    
    batch_config = {
        "trade_date": trade_date,
        "factor_list": ["momentum_5d", "pe_percentile"],
        "weights": {
            "momentum_5d": 0.6,
            "pe_percentile": 0.4
        },
        "method": "factor_weight",
        "top_n": 10
    }
    
    response = requests.post(f"{BASE_URL}/batch/calculate-and-score", json=batch_config)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 批量工作流程完成")
        print_result(result)
        return True
    else:
        print(f"❌ 批量工作流程失败: {response.text}")
        return False

def main():
    """主函数"""
    print("🚀 多因子模型系统演示开始")
    print(f"📅 演示时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 1. 计算因子
        if not demo_factor_calculation():
            print("⚠️  因子计算失败，但继续演示其他功能")
        
        time.sleep(2)
        
        # 2. 创建模型
        if demo_model_creation():
            time.sleep(2)
            
            # 3. 训练模型
            if not demo_model_training():
                print("⚠️  模型训练失败，跳过ML相关演示")
        
        time.sleep(2)
        
        # 4. 基于因子的评分
        factor_stocks = demo_factor_based_scoring()
        
        time.sleep(2)
        
        # 5. 基于ML的评分（如果模型训练成功）
        ml_stocks = demo_ml_based_scoring()
        
        time.sleep(2)
        
        # 6. 投资组合优化
        demo_portfolio_optimization()
        
        time.sleep(2)
        
        # 7. 批量工作流程
        demo_batch_workflow()
        
        print_step("演示完成")
        print("✅ 多因子模型系统演示成功完成！")
        print("\n📋 演示总结:")
        print("1. ✅ 因子计算 - 计算了所有内置因子")
        print("2. ✅ 模型创建 - 创建了随机森林模型")
        print("3. ⚠️  模型训练 - 可能因数据不足而失败")
        print("4. ✅ 因子评分 - 基于因子权重进行股票评分")
        print("5. ⚠️  ML评分 - 依赖于模型训练结果")
        print("6. ✅ 组合优化 - 集成选股和组合优化")
        print("7. ✅ 批量流程 - 一键完成计算和评分")
        
        print("\n🌐 访问Web界面:")
        print("- 因子管理: http://127.0.0.1:5001/ml-factor")
        print("- 模型管理: http://127.0.0.1:5001/ml-factor/models")
        print("- 股票评分: http://127.0.0.1:5001/ml-factor/scoring")
        print("- 投资组合: http://127.0.0.1:5001/ml-factor/portfolio")
        
    except Exception as e:
        print(f"❌ 演示过程中发生错误: {e}")
        return False
    
    return True

if __name__ == '__main__':
    main() 