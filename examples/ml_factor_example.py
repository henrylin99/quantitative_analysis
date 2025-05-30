"""
多因子选股和机器学习模型使用示例
"""

import requests
import json
from datetime import datetime, timedelta

# API基础URL
BASE_URL = "http://localhost:5000/api/ml-factor"

def example_1_create_custom_factor():
    """示例1: 创建自定义因子"""
    print("=== 示例1: 创建自定义因子 ===")
    
    # 创建一个自定义动量因子
    factor_data = {
        "factor_id": "momentum_10d_custom",
        "factor_name": "自定义10日动量",
        "factor_formula": "close.pct_change(10)",
        "factor_type": "momentum",
        "description": "自定义的10日价格变化率因子",
        "params": {"period": 10}
    }
    
    response = requests.post(f"{BASE_URL}/factors/custom", json=factor_data)
    print(f"创建自定义因子结果: {response.json()}")

def example_2_calculate_factors():
    """示例2: 计算因子值"""
    print("\n=== 示例2: 计算因子值 ===")
    
    # 计算指定因子
    calc_data = {
        "trade_date": "2024-01-15",
        "factor_ids": ["momentum_1d", "momentum_5d", "volatility_20d"],
        "ts_codes": ["000001.SZ", "000002.SZ", "600000.SH"]  # 可选，不指定则计算所有股票
    }
    
    response = requests.post(f"{BASE_URL}/factors/calculate", json=calc_data)
    print(f"计算因子结果: {response.json()}")

def example_3_create_ml_model():
    """示例3: 创建机器学习模型"""
    print("\n=== 示例3: 创建机器学习模型 ===")
    
    # 创建随机森林模型
    model_data = {
        "model_id": "rf_model_v1",
        "model_name": "随机森林选股模型V1",
        "model_type": "random_forest",
        "factor_list": [
            "momentum_1d", "momentum_5d", "momentum_20d",
            "volatility_20d", "rsi_14d", "ma_ratio_5_20",
            "turnover_rate_20d", "volume_ratio_5_20"
        ],
        "target_type": "return_5d",  # 预测5日收益率
        "model_params": {
            "n_estimators": 200,
            "max_depth": 15,
            "min_samples_split": 10,
            "random_state": 42
        },
        "training_config": {
            "test_size": 0.2,
            "validation_method": "time_series_split",
            "cv_folds": 5,
            "feature_selection": True,
            "feature_selection_k": 15,
            "scaling_method": "robust"
        }
    }
    
    response = requests.post(f"{BASE_URL}/models/create", json=model_data)
    print(f"创建模型结果: {response.json()}")

def example_4_train_model():
    """示例4: 训练机器学习模型"""
    print("\n=== 示例4: 训练机器学习模型 ===")
    
    # 训练模型
    train_data = {
        "model_id": "rf_model_v1",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31"
    }
    
    response = requests.post(f"{BASE_URL}/models/train", json=train_data)
    result = response.json()
    print(f"训练模型结果: {result}")
    
    if result.get('success'):
        print(f"训练指标: {json.dumps(result['metrics'], indent=2, ensure_ascii=False)}")

def example_5_model_prediction():
    """示例5: 模型预测"""
    print("\n=== 示例5: 模型预测 ===")
    
    # 使用模型进行预测
    predict_data = {
        "model_id": "rf_model_v1",
        "trade_date": "2024-01-15",
        "ts_codes": None  # 不指定则预测所有股票
    }
    
    response = requests.post(f"{BASE_URL}/models/predict", json=predict_data)
    result = response.json()
    print(f"预测结果: {result}")
    
    if result.get('success'):
        predictions = result['predictions'][:5]  # 显示前5个预测结果
        print(f"前5个预测结果: {json.dumps(predictions, indent=2, ensure_ascii=False)}")

def example_6_factor_based_scoring():
    """示例6: 基于因子的股票打分"""
    print("\n=== 示例6: 基于因子的股票打分 ===")
    
    # 因子权重打分
    scoring_data = {
        "trade_date": "2024-01-15",
        "factor_list": [
            "momentum_5d", "momentum_20d", "volatility_20d",
            "rsi_14d", "ma_ratio_5_20", "turnover_rate_20d"
        ],
        "weights": {
            "momentum_5d": 0.2,
            "momentum_20d": 0.2,
            "volatility_20d": -0.1,  # 负权重，低波动率更好
            "rsi_14d": 0.15,
            "ma_ratio_5_20": 0.25,
            "turnover_rate_20d": 0.2
        },
        "method": "factor_weight",
        "top_n": 20,
        "filters": {
            "min_percentile": 70,  # 只选择排名前30%的股票
            "exclude_codes": ["000001.SZ"]  # 排除某些股票
        }
    }
    
    response = requests.post(f"{BASE_URL}/scoring/factor-based", json=scoring_data)
    result = response.json()
    print(f"因子打分结果: {result}")
    
    if result.get('success'):
        top_stocks = result['top_stocks'][:10]  # 显示前10只股票
        print(f"前10只股票: {json.dumps(top_stocks, indent=2, ensure_ascii=False)}")

def example_7_ml_based_selection():
    """示例7: 基于机器学习的股票选择"""
    print("\n=== 示例7: 基于机器学习的股票选择 ===")
    
    # 多模型集成选股
    selection_data = {
        "trade_date": "2024-01-15",
        "model_ids": ["rf_model_v1"],  # 可以添加多个模型
        "top_n": 30,
        "ensemble_method": "average"  # 平均集成
    }
    
    response = requests.post(f"{BASE_URL}/scoring/ml-based", json=selection_data)
    result = response.json()
    print(f"ML选股结果: {result}")
    
    if result.get('success'):
        top_stocks = result['top_stocks'][:10]  # 显示前10只股票
        print(f"前10只股票: {json.dumps(top_stocks, indent=2, ensure_ascii=False)}")

def example_8_factor_contribution_analysis():
    """示例8: 因子贡献度分析"""
    print("\n=== 示例8: 因子贡献度分析 ===")
    
    # 分析特定股票的因子贡献度
    analysis_data = {
        "ts_code": "000001.SZ",
        "trade_date": "2024-01-15",
        "factor_list": [
            "momentum_5d", "momentum_20d", "volatility_20d",
            "rsi_14d", "ma_ratio_5_20", "pe_ttm", "pb_ratio"
        ]
    }
    
    response = requests.post(f"{BASE_URL}/analysis/factor-contribution", json=analysis_data)
    result = response.json()
    print(f"因子贡献度分析结果: {result}")
    
    if result.get('success'):
        contributions = result['analysis']['factor_contributions']
        print(f"因子贡献度: {json.dumps(contributions, indent=2, ensure_ascii=False)}")

def example_9_sector_analysis():
    """示例9: 行业分析"""
    print("\n=== 示例9: 行业分析 ===")
    
    # 行业层面的因子分析
    analysis_data = {
        "trade_date": "2024-01-15",
        "factor_list": [
            "momentum_5d", "momentum_20d", "volatility_20d",
            "rsi_14d", "ma_ratio_5_20", "turnover_rate_20d"
        ],
        "top_n": 5  # 显示前5个行业
    }
    
    response = requests.post(f"{BASE_URL}/analysis/sector", json=analysis_data)
    result = response.json()
    print(f"行业分析结果: {result}")
    
    if result.get('success'):
        industry_summary = result['analysis']['industry_summary'][:3]  # 显示前3个行业
        print(f"前3个行业摘要: {json.dumps(industry_summary, indent=2, ensure_ascii=False)}")

def example_10_batch_operations():
    """示例10: 批量操作"""
    print("\n=== 示例10: 批量操作 ===")
    
    # 批量计算因子并打分
    batch_data = {
        "trade_date": "2024-01-15",
        "factor_list": [
            "momentum_1d", "momentum_5d", "volatility_20d",
            "rsi_14d", "ma_ratio_5_20"
        ],
        "weights": {
            "momentum_1d": 0.1,
            "momentum_5d": 0.3,
            "volatility_20d": -0.2,
            "rsi_14d": 0.2,
            "ma_ratio_5_20": 0.2
        },
        "method": "factor_weight",
        "top_n": 15
    }
    
    response = requests.post(f"{BASE_URL}/batch/calculate-and-score", json=batch_data)
    result = response.json()
    print(f"批量操作结果: {result}")
    
    if result.get('success'):
        top_stocks = result['top_stocks'][:5]  # 显示前5只股票
        print(f"前5只股票: {json.dumps(top_stocks, indent=2, ensure_ascii=False)}")

def example_11_model_evaluation():
    """示例11: 模型评估"""
    print("\n=== 示例11: 模型评估 ===")
    
    # 评估模型性能
    eval_data = {
        "model_id": "rf_model_v1",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31"
    }
    
    response = requests.post(f"{BASE_URL}/models/evaluate", json=eval_data)
    result = response.json()
    print(f"模型评估结果: {result}")
    
    if result.get('success'):
        metrics = result['metrics']
        print(f"评估指标: {json.dumps(metrics, indent=2, ensure_ascii=False)}")

def example_12_get_lists():
    """示例12: 获取列表信息"""
    print("\n=== 示例12: 获取列表信息 ===")
    
    # 获取因子列表
    response = requests.get(f"{BASE_URL}/factors/list?factor_type=momentum")
    print(f"动量因子列表: {response.json()}")
    
    # 获取模型列表
    response = requests.get(f"{BASE_URL}/models/list")
    print(f"模型列表: {response.json()}")

def run_all_examples():
    """运行所有示例"""
    print("开始运行多因子选股和机器学习模型示例...")
    
    try:
        # 基础操作
        example_1_create_custom_factor()
        example_2_calculate_factors()
        
        # 机器学习模型
        example_3_create_ml_model()
        example_4_train_model()
        example_5_model_prediction()
        
        # 股票选择和打分
        example_6_factor_based_scoring()
        example_7_ml_based_selection()
        
        # 分析功能
        example_8_factor_contribution_analysis()
        example_9_sector_analysis()
        
        # 批量操作和评估
        example_10_batch_operations()
        example_11_model_evaluation()
        
        # 列表查询
        example_12_get_lists()
        
        print("\n所有示例运行完成！")
        
    except requests.exceptions.ConnectionError:
        print("错误: 无法连接到API服务器，请确保服务器正在运行")
    except Exception as e:
        print(f"运行示例时出错: {e}")

if __name__ == "__main__":
    # 可以运行单个示例或所有示例
    import sys
    
    if len(sys.argv) > 1:
        example_num = sys.argv[1]
        example_func = f"example_{example_num}"
        if example_func in globals():
            globals()[example_func]()
        else:
            print(f"示例 {example_num} 不存在")
    else:
        run_all_examples() 