#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子选股系统完整使用示例

本示例展示了从因子计算、模型训练、股票选择、组合优化到回测验证的完整流程
"""

import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import time

# API基础URL
BASE_URL = 'http://localhost:5000/api/ml-factor'

class MLFactorSystemDemo:
    """多因子选股系统演示"""
    
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        
    def demo_factor_management(self):
        """演示因子管理功能"""
        print("=" * 60)
        print("1. 因子管理演示")
        print("=" * 60)
        
        # 1.1 获取因子列表
        print("\n1.1 获取现有因子列表:")
        response = self.session.get(f"{self.base_url}/factors/list")
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"共有 {data['total_count']} 个因子:")
                for factor in data['factors'][:5]:  # 只显示前5个
                    print(f"  - {factor['factor_id']}: {factor['factor_name']} ({factor['factor_type']})")
            else:
                print(f"获取因子列表失败: {data.get('error')}")
        else:
            print(f"请求失败: {response.status_code}")
        
        # 1.2 创建自定义因子
        print("\n1.2 创建自定义因子:")
        custom_factor = {
            "factor_id": "custom_momentum_30d",
            "factor_name": "30日动量因子",
            "factor_type": "momentum",
            "factor_formula": "close.pct_change(30)",
            "description": "计算30日价格变化率作为动量指标"
        }
        
        response = self.session.post(
            f"{self.base_url}/factors/custom",
            json=custom_factor
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 成功创建自定义因子: {custom_factor['factor_id']}")
            else:
                print(f"✗ 创建因子失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 1.3 计算因子值
        print("\n1.3 计算因子值:")
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        calc_request = {
            "trade_date": yesterday,
            "factor_ids": ["momentum_1d", "momentum_5d", "volatility_20d"]
        }
        
        response = self.session.post(
            f"{self.base_url}/factors/calculate",
            json=calc_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 成功计算 {yesterday} 的因子值:")
                for result in data['results']:
                    if 'calculated_count' in result:
                        print(f"  - {result['factor_id']}: {result['calculated_count']} 只股票")
                    else:
                        print(f"  - {result['factor_id']}: 计算失败 - {result.get('error')}")
            else:
                print(f"✗ 计算因子失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
    
    def demo_model_management(self):
        """演示模型管理功能"""
        print("\n" + "=" * 60)
        print("2. 模型管理演示")
        print("=" * 60)
        
        # 2.1 创建机器学习模型
        print("\n2.1 创建机器学习模型:")
        model_config = {
            "model_id": "demo_xgb_model",
            "model_name": "演示XGBoost模型",
            "model_type": "xgboost",
            "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d", "rsi_14", "turnover_rate"],
            "target_type": "return_5d",
            "model_params": {
                "n_estimators": 100,
                "max_depth": 6,
                "learning_rate": 0.1
            }
        }
        
        response = self.session.post(
            f"{self.base_url}/models/create",
            json=model_config
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 成功创建模型: {model_config['model_id']}")
            else:
                print(f"✗ 创建模型失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 2.2 训练模型
        print("\n2.2 训练模型 (这可能需要几分钟):")
        train_request = {
            "model_id": "demo_xgb_model",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31"
        }
        
        response = self.session.post(
            f"{self.base_url}/models/train",
            json=train_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 模型训练完成")
                print(f"  训练指标: {data.get('metrics', {})}")
            else:
                print(f"✗ 模型训练失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 2.3 模型预测
        print("\n2.3 使用模型进行预测:")
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        predict_request = {
            "model_id": "demo_xgb_model",
            "trade_date": yesterday
        }
        
        response = self.session.post(
            f"{self.base_url}/models/predict",
            json=predict_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 预测完成: {data.get('message')}")
                predictions = data.get('predictions', [])
                if predictions:
                    print(f"  前5个预测结果:")
                    for pred in predictions[:5]:
                        print(f"    {pred['ts_code']}: {pred['predicted_value']:.4f}")
            else:
                print(f"✗ 预测失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
    
    def demo_stock_selection(self):
        """演示股票选择功能"""
        print("\n" + "=" * 60)
        print("3. 股票选择演示")
        print("=" * 60)
        
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 3.1 基于因子的选股
        print("\n3.1 基于因子的选股:")
        factor_selection = {
            "trade_date": yesterday,
            "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"],
            "method": "equal_weight",
            "top_n": 20
        }
        
        response = self.session.post(
            f"{self.base_url}/scoring/factor-based",
            json=factor_selection
        )
        
        factor_stocks = []
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 基于因子选出 {data['selected_stocks']} 只股票")
                factor_stocks = data['top_stocks']
                print("  前5只股票:")
                for stock in factor_stocks[:5]:
                    print(f"    {stock['ts_code']}: 分数={stock['composite_score']:.4f}, 排名={stock['rank']}")
            else:
                print(f"✗ 因子选股失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 3.2 基于ML模型的选股
        print("\n3.2 基于ML模型的选股:")
        ml_selection = {
            "trade_date": yesterday,
            "model_ids": ["demo_xgb_model"],
            "top_n": 20,
            "ensemble_method": "average"
        }
        
        response = self.session.post(
            f"{self.base_url}/scoring/ml-based",
            json=ml_selection
        )
        
        ml_stocks = []
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 基于ML模型选出 {data['selected_stocks']} 只股票")
                ml_stocks = data['top_stocks']
                print("  前5只股票:")
                for stock in ml_stocks[:5]:
                    print(f"    {stock['ts_code']}: 分数={stock['ensemble_score']:.4f}, 排名={stock['rank']}")
            else:
                print(f"✗ ML选股失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        return factor_stocks, ml_stocks
    
    def demo_portfolio_optimization(self, selected_stocks):
        """演示组合优化功能"""
        print("\n" + "=" * 60)
        print("4. 组合优化演示")
        print("=" * 60)
        
        if not selected_stocks:
            print("✗ 没有选中的股票，跳过组合优化")
            return None
        
        # 构建预期收益率
        expected_returns = {}
        for stock in selected_stocks:
            score = stock.get('composite_score', stock.get('ensemble_score', 0))
            expected_returns[stock['ts_code']] = score
        
        # 4.1 等权重优化
        print("\n4.1 等权重组合优化:")
        equal_weight_request = {
            "expected_returns": expected_returns,
            "method": "equal_weight"
        }
        
        response = self.session.post(
            f"{self.base_url}/portfolio/optimize",
            json=equal_weight_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 等权重优化完成")
                stats = data['portfolio_stats']
                print(f"  预期收益率: {stats['expected_return']:.4f}")
                print(f"  预期风险: {stats['expected_risk']:.4f}")
                print(f"  夏普比率: {stats['sharpe_ratio']:.4f}")
                print(f"  有效股票数: {stats['effective_stocks']:.1f}")
            else:
                print(f"✗ 等权重优化失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 4.2 均值-方差优化
        print("\n4.2 均值-方差组合优化:")
        mv_request = {
            "expected_returns": expected_returns,
            "method": "mean_variance",
            "constraints": {
                "max_weight": 0.1,  # 最大权重10%
                "risk_aversion": 1.0
            }
        }
        
        response = self.session.post(
            f"{self.base_url}/portfolio/optimize",
            json=mv_request
        )
        
        optimized_portfolio = None
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 均值-方差优化完成")
                stats = data['portfolio_stats']
                print(f"  预期收益率: {stats['expected_return']:.4f}")
                print(f"  预期风险: {stats['expected_risk']:.4f}")
                print(f"  夏普比率: {stats['sharpe_ratio']:.4f}")
                print(f"  最大权重: {stats['max_weight']:.4f}")
                
                # 显示前5个权重
                weights = data['weights']
                sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
                print("  前5个权重:")
                for ts_code, weight in sorted_weights[:5]:
                    print(f"    {ts_code}: {weight:.4f}")
                
                optimized_portfolio = data
            else:
                print(f"✗ 均值-方差优化失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        return optimized_portfolio
    
    def demo_integrated_selection(self):
        """演示集成选股和组合优化"""
        print("\n" + "=" * 60)
        print("5. 集成选股和组合优化演示")
        print("=" * 60)
        
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        integrated_request = {
            "trade_date": yesterday,
            "selection_method": "factor_based",
            "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"],
            "top_n": 30,
            "optimization_method": "mean_variance",
            "constraints": {
                "max_weight": 0.08,
                "risk_aversion": 1.5
            }
        }
        
        response = self.session.post(
            f"{self.base_url}/portfolio/integrated-selection",
            json=integrated_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 集成选股和组合优化完成")
                print(f"  选股方法: {data['selection_method']}")
                print(f"  优化方法: {data['optimization_method']}")
                print(f"  候选股票数: {data['stock_selection']['total_candidates']}")
                
                portfolio_stats = data['portfolio_optimization']['portfolio_stats']
                print(f"  组合预期收益率: {portfolio_stats['expected_return']:.4f}")
                print(f"  组合预期风险: {portfolio_stats['expected_risk']:.4f}")
                print(f"  组合夏普比率: {portfolio_stats['sharpe_ratio']:.4f}")
                
                return data
            else:
                print(f"✗ 集成优化失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        return None
    
    def demo_backtest(self):
        """演示回测功能"""
        print("\n" + "=" * 60)
        print("6. 回测验证演示")
        print("=" * 60)
        
        # 6.1 单策略回测
        print("\n6.1 单策略回测:")
        strategy_config = {
            "selection_method": "factor_based",
            "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"],
            "top_n": 30,
            "optimization": {
                "method": "equal_weight"
            },
            "transaction_cost": 0.001
        }
        
        backtest_request = {
            "strategy_config": strategy_config,
            "start_date": "2023-01-01",
            "end_date": "2023-06-30",
            "initial_capital": 1000000.0,
            "rebalance_frequency": "monthly"
        }
        
        response = self.session.post(
            f"{self.base_url}/backtest/run",
            json=backtest_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 回测完成")
                print(f"  回测期间: {data['backtest_period']}")
                print(f"  初始资金: {data['initial_capital']:,.0f}")
                print(f"  最终价值: {data['final_value']:,.0f}")
                print(f"  总收益率: {data['total_return']:.4f}")
                
                metrics = data['performance_metrics']
                print(f"  年化收益率: {metrics['annualized_return']:.4f}")
                print(f"  年化波动率: {metrics['volatility']:.4f}")
                print(f"  夏普比率: {metrics['sharpe_ratio']:.4f}")
                print(f"  最大回撤: {metrics['max_drawdown']:.4f}")
                print(f"  胜率: {metrics['win_rate']:.4f}")
            else:
                print(f"✗ 回测失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 6.2 策略比较
        print("\n6.2 多策略比较:")
        strategies = [
            {
                "name": "等权重策略",
                "config": {
                    "selection_method": "factor_based",
                    "factor_list": ["momentum_1d", "momentum_5d"],
                    "top_n": 20,
                    "optimization": {"method": "equal_weight"}
                }
            },
            {
                "name": "均值方差策略",
                "config": {
                    "selection_method": "factor_based",
                    "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"],
                    "top_n": 30,
                    "optimization": {
                        "method": "mean_variance",
                        "constraints": {"max_weight": 0.1}
                    }
                }
            }
        ]
        
        compare_request = {
            "strategies": strategies,
            "start_date": "2023-01-01",
            "end_date": "2023-06-30"
        }
        
        response = self.session.post(
            f"{self.base_url}/backtest/compare",
            json=compare_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 策略比较完成")
                comparison = data['comparison']
                print(f"  比较策略数: {comparison['summary']['total_strategies']}")
                print(f"  平均收益率: {comparison['summary']['avg_return']:.4f}")
                print(f"  平均夏普比率: {comparison['summary']['avg_sharpe']:.4f}")
                
                best = comparison['best_strategy']
                print(f"  最高收益策略: {best['highest_return']}")
                print(f"  最高夏普策略: {best['highest_sharpe']}")
            else:
                print(f"✗ 策略比较失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
    
    def demo_analysis(self):
        """演示分析功能"""
        print("\n" + "=" * 60)
        print("7. 分析功能演示")
        print("=" * 60)
        
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 7.1 行业分析
        print("\n7.1 行业分析:")
        sector_request = {
            "trade_date": yesterday,
            "factor_list": ["momentum_1d", "momentum_5d"],
            "top_n": 10
        }
        
        response = self.session.post(
            f"{self.base_url}/analysis/sector",
            json=sector_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 行业分析完成")
                analysis = data['analysis']
                if 'industry_summary' in analysis:
                    print("  行业表现排名:")
                    for i, industry in enumerate(analysis['industry_summary'][:5]):
                        print(f"    {i+1}. {industry['industry']}: "
                              f"平均分数={industry['composite_score_mean']:.4f}, "
                              f"股票数={industry['composite_score_count']}")
            else:
                print(f"✗ 行业分析失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
        
        # 7.2 因子贡献度分析
        print("\n7.2 因子贡献度分析:")
        contribution_request = {
            "ts_code": "000001.SZ",  # 平安银行
            "trade_date": yesterday,
            "factor_list": ["momentum_1d", "momentum_5d", "volatility_20d"]
        }
        
        response = self.session.post(
            f"{self.base_url}/analysis/factor-contribution",
            json=contribution_request
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print(f"✓ 因子贡献度分析完成")
                analysis = data['analysis']
                print(f"  股票: {contribution_request['ts_code']}")
                if 'factor_contributions' in analysis:
                    print("  因子贡献度:")
                    for factor_id, contribution in analysis['factor_contributions'].items():
                        print(f"    {factor_id}: {contribution:.4f}")
            else:
                print(f"✗ 因子贡献度分析失败: {data.get('error')}")
        else:
            print(f"✗ 请求失败: {response.status_code}")
    
    def run_complete_demo(self):
        """运行完整演示"""
        print("多因子选股系统完整演示")
        print("=" * 60)
        print("本演示将展示系统的所有主要功能:")
        print("1. 因子管理 (创建、计算)")
        print("2. 模型管理 (创建、训练、预测)")
        print("3. 股票选择 (因子选股、ML选股)")
        print("4. 组合优化 (等权重、均值-方差)")
        print("5. 集成选股和优化")
        print("6. 回测验证 (单策略、多策略比较)")
        print("7. 分析功能 (行业分析、因子贡献度)")
        print("\n开始演示...")
        
        try:
            # 1. 因子管理
            self.demo_factor_management()
            
            # 2. 模型管理
            self.demo_model_management()
            
            # 3. 股票选择
            factor_stocks, ml_stocks = self.demo_stock_selection()
            
            # 4. 组合优化
            if factor_stocks:
                optimized_portfolio = self.demo_portfolio_optimization(factor_stocks)
            
            # 5. 集成选股和优化
            integrated_result = self.demo_integrated_selection()
            
            # 6. 回测验证
            self.demo_backtest()
            
            # 7. 分析功能
            self.demo_analysis()
            
            print("\n" + "=" * 60)
            print("演示完成！")
            print("=" * 60)
            print("系统功能总结:")
            print("✓ 因子管理: 支持内置和自定义因子")
            print("✓ 模型管理: 支持多种机器学习算法")
            print("✓ 股票选择: 基于因子和ML模型的选股")
            print("✓ 组合优化: 多种优化方法和约束条件")
            print("✓ 回测验证: 完整的策略回测和比较")
            print("✓ 分析功能: 行业分析和因子贡献度分析")
            print("\n系统已准备就绪，可以开始实际使用！")
            
        except Exception as e:
            print(f"\n演示过程中出现错误: {e}")
            print("请检查系统是否正常运行")


def main():
    """主函数"""
    print("多因子选股系统完整演示")
    print("请确保系统已启动并运行在 http://localhost:5000")
    
    # 等待用户确认
    input("\n按回车键开始演示...")
    
    # 创建演示实例
    demo = MLFactorSystemDemo()
    
    # 运行完整演示
    demo.run_complete_demo()


if __name__ == "__main__":
    main() 