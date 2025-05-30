#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多因子模型系统完整功能演示
展示从因子计算到投资组合构建的完整流程
"""

import requests
import json
import time
from datetime import datetime

# API基础URL
BASE_URL = "http://127.0.0.1:5001/api/ml-factor"

def print_section(title):
    """打印章节标题"""
    print(f"\n{'='*80}")
    print(f"🎯 {title}")
    print(f"{'='*80}")

def print_subsection(title):
    """打印子章节标题"""
    print(f"\n{'─'*60}")
    print(f"📊 {title}")
    print(f"{'─'*60}")

def print_result(data, title="结果"):
    """格式化打印结果"""
    print(f"\n✅ {title}:")
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                print(f"  {key}: {len(value) if isinstance(value, list) else 'dict'}")
            else:
                print(f"  {key}: {value}")
    else:
        print(f"  {data}")

def demo_factor_management():
    """演示因子管理功能"""
    print_section("1. 因子管理功能演示")
    
    # 1.1 获取因子列表
    print_subsection("1.1 获取因子列表")
    response = requests.get(f"{BASE_URL}/factors/list")
    if response.status_code == 200:
        data = response.json()
        print_result({
            "总因子数量": data['total_count'],
            "内置因子": len([f for f in data['factors'] if f['is_builtin']]),
            "自定义因子": len([f for f in data['factors'] if not f['is_builtin']]),
            "技术面因子": len([f for f in data['factors'] if f['factor_type'] == 'technical']),
            "基本面因子": len([f for f in data['factors'] if f['factor_type'] == 'fundamental']),
            "资金面因子": len([f for f in data['factors'] if f['factor_type'] == 'money_flow']),
            "筹码面因子": len([f for f in data['factors'] if f['factor_type'] == 'chip'])
        })
    
    # 1.2 计算关键因子
    print_subsection("1.2 计算关键因子")
    trade_date = "2025-05-23"
    key_factors = ["money_flow_strength", "chip_concentration"]
    
    for factor_id in key_factors:
        response = requests.post(f"{BASE_URL}/factors/calculate", json={
            "trade_date": trade_date,
            "factor_ids": [factor_id],
            "ts_codes": []
        })
        
        if response.status_code == 200:
            data = response.json()
            result = data['results'][0]
            print(f"  ✓ {factor_id}: 计算了 {result['calculated_count']} 只股票")
        else:
            print(f"  ✗ {factor_id}: 计算失败")

def demo_stock_scoring():
    """演示股票评分功能"""
    print_section("2. 股票评分功能演示")
    
    # 2.1 单因子评分
    print_subsection("2.1 基于单因子的股票评分")
    response = requests.post(f"{BASE_URL}/scoring/factor-based", json={
        "trade_date": "2025-05-23",
        "factor_list": ["money_flow_strength"],
        "weights": {"money_flow_strength": 1.0},
        "method": "factor_weight",
        "top_n": 5
    })
    
    if response.status_code == 200:
        data = response.json()
        print_result({
            "评分方法": data['method'],
            "总股票数": data['total_stocks'],
            "选出股票数": data['selected_stocks']
        })
        
        print("\n🏆 前5名股票:")
        for i, stock in enumerate(data['top_stocks'][:5], 1):
            print(f"  {i}. {stock['name']}({stock['ts_code']}) - 评分: {stock['composite_score']:.4f}")
    
    # 2.2 多因子加权评分
    print_subsection("2.2 基于多因子加权的股票评分")
    response = requests.post(f"{BASE_URL}/scoring/factor-based", json={
        "trade_date": "2025-05-23",
        "factor_list": ["money_flow_strength", "chip_concentration"],
        "weights": {"money_flow_strength": 0.6, "chip_concentration": 0.4},
        "method": "factor_weight",
        "top_n": 10
    })
    
    if response.status_code == 200:
        data = response.json()
        print_result({
            "评分方法": data['method'],
            "因子权重": "资金流向强度(60%) + 筹码集中度(40%)",
            "总股票数": data['total_stocks'],
            "选出股票数": data['selected_stocks']
        })
        
        print("\n🏆 前10名股票:")
        for i, stock in enumerate(data['top_stocks'], 1):
            print(f"  {i:2d}. {stock['name']:8s}({stock['ts_code']}) - 评分: {stock['composite_score']:.4f}")

def demo_portfolio_optimization():
    """演示投资组合优化功能"""
    print_section("3. 投资组合优化功能演示")
    
    # 3.1 等权重组合
    print_subsection("3.1 等权重投资组合")
    response = requests.post(f"{BASE_URL}/portfolio/integrated-selection", json={
        "trade_date": "2025-05-23",
        "selection_method": "factor_based",
        "factor_list": ["money_flow_strength", "chip_concentration"],
        "weights": {"money_flow_strength": 0.6, "chip_concentration": 0.4},
        "top_n": 10,
        "optimization_method": "equal_weight"
    })
    
    if response.status_code == 200:
        data = response.json()
        portfolio_stats = data['portfolio_optimization']['portfolio_stats']
        
        print_result({
            "选股方法": data['selection_method'],
            "优化方法": data['optimization_method'],
            "股票数量": data['portfolio_optimization']['total_stocks'],
            "预期收益": f"{portfolio_stats['expected_return']:.4f}",
            "预期风险": f"{portfolio_stats['expected_risk']:.4f}",
            "夏普比率": f"{portfolio_stats['sharpe_ratio']:.2f}",
            "集中度(HHI)": f"{portfolio_stats['concentration_hhi']:.4f}",
            "有效股票数": f"{portfolio_stats['effective_stocks']:.1f}"
        })
        
        print("\n📈 投资组合权重:")
        weights = data['final_portfolio']['weights']
        for ts_code, weight in weights.items():
            print(f"  {ts_code}: {weight:.1%}")

def main():
    """主函数"""
    print("🚀 多因子模型系统完整功能演示")
    print("=" * 80)
    
    try:
        # 检查系统状态
        response = requests.get("http://127.0.0.1:5001/")
        if response.status_code != 200:
            print("❌ 系统未启动，请先运行 python run.py")
            return
        
        print("✅ 系统运行正常，开始演示...")
        
        # 执行各个功能演示
        demo_factor_management()
        time.sleep(1)
        
        demo_stock_scoring()
        time.sleep(1)
        
        demo_portfolio_optimization()
        
        print_section("系统功能总结")
        print("""
🎉 多因子模型系统功能演示完成！

✅ 已实现的核心功能:
   📊 因子管理: 36个内置因子 + 自定义因子支持
   🔢 因子计算: 技术面、基本面、资金面、筹码面因子
   📈 股票评分: 单因子/多因子加权评分
   💼 投资组合: 等权重、均值方差、风险平价优化
   🔄 再平衡: 交易指令生成和成本计算
   ⚡ 批量处理: 一键完成因子计算到选股的全流程

🔧 技术特点:
   🚀 基于真实股票数据 (81万+行情记录)
   📊 完整的因子值标准化 (Z-score + 百分位排名)
   🎯 多种投资组合优化算法
   💾 数据持久化存储
   🌐 RESTful API接口
   🖥️ 现代化Web界面

📱 访问方式:
   🏠 首页: http://127.0.0.1:5001/
   📊 因子管理: http://127.0.0.1:5001/ml-factor
   🤖 模型管理: http://127.0.0.1:5001/ml-factor/models
   📈 股票评分: http://127.0.0.1:5001/ml-factor/scoring
   💼 投资组合: http://127.0.0.1:5001/ml-factor/portfolio

🎯 系统已准备就绪，可以开始实际的量化投资研究！
        """)
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到系统，请确保应用正在运行 (python run.py)")
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")

if __name__ == "__main__":
    main() 