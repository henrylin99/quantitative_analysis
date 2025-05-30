#!/usr/bin/env python3
"""
风险管理模块测试脚本
测试实时风险管理的各项功能
"""

import requests
import json
import time
from datetime import datetime

# 测试配置
BASE_URL = "http://127.0.0.1:5001"
PORTFOLIO_ID = "demo_portfolio"

def test_api_endpoint(endpoint, method='GET', data=None, description=""):
    """测试API接口"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == 'GET':
            response = requests.get(url, timeout=10)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=10)
        elif method == 'PUT':
            response = requests.put(url, json=data, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, timeout=10)
        
        result = response.json()
        
        if response.status_code == 200 and result.get('success'):
            print(f"✅ {description}: 成功")
            return result
        else:
            print(f"❌ {description}: 失败 - {result.get('message', '未知错误')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ {description}: 网络错误 - {str(e)}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ {description}: JSON解析错误 - {str(e)}")
        return None

def test_create_sample_portfolio():
    """创建示例投资组合"""
    print("\n=== 创建示例投资组合 ===")
    
    # 示例持仓数据
    positions = [
        {
            "portfolio_id": PORTFOLIO_ID,
            "ts_code": "000001.SZ",
            "position_size": 1000,
            "avg_cost": 12.50,
            "sector": "银行"
        },
        {
            "portfolio_id": PORTFOLIO_ID,
            "ts_code": "000002.SZ", 
            "position_size": 500,
            "avg_cost": 25.80,
            "sector": "房地产"
        },
        {
            "portfolio_id": PORTFOLIO_ID,
            "ts_code": "600000.SH",
            "position_size": 800,
            "avg_cost": 8.90,
            "sector": "银行"
        },
        {
            "portfolio_id": PORTFOLIO_ID,
            "ts_code": "600036.SH",
            "position_size": 300,
            "avg_cost": 35.20,
            "sector": "银行"
        },
        {
            "portfolio_id": PORTFOLIO_ID,
            "ts_code": "000858.SZ",
            "position_size": 600,
            "avg_cost": 18.60,
            "sector": "食品饮料"
        }
    ]
    
    success_count = 0
    for position in positions:
        result = test_api_endpoint(
            "/api/realtime-analysis/risk/portfolio",
            method='POST',
            data=position,
            description=f"创建持仓 {position['ts_code']}"
        )
        if result:
            success_count += 1
    
    print(f"成功创建 {success_count}/{len(positions)} 个持仓")
    return success_count > 0

def test_portfolio_positions():
    """测试获取投资组合持仓"""
    print("\n=== 测试投资组合持仓 ===")
    
    result = test_api_endpoint(
        f"/api/realtime-analysis/risk/portfolio/{PORTFOLIO_ID}/positions",
        description="获取投资组合持仓"
    )
    
    if result and result.get('data'):
        positions = result['data']['positions']
        print(f"📊 持仓数量: {len(positions)}")
        for pos in positions[:3]:  # 显示前3个持仓
            print(f"   {pos['ts_code']}: {pos['position_size']}股, 成本价¥{pos['avg_cost']}")
    
    return result is not None

def test_portfolio_metrics():
    """测试投资组合指标"""
    print("\n=== 测试投资组合指标 ===")
    
    result = test_api_endpoint(
        f"/api/realtime-analysis/risk/portfolio/{PORTFOLIO_ID}/metrics",
        description="获取投资组合指标"
    )
    
    if result and result.get('data'):
        metrics = result['data']
        print(f"📈 总市值: ¥{metrics.get('total_market_value', 0):,.2f}")
        print(f"📊 总盈亏: ¥{metrics.get('total_unrealized_pnl', 0):,.2f}")
        print(f"📋 持仓数量: {metrics.get('total_positions', 0)}")
        
        # 显示行业分布
        sector_dist = metrics.get('sector_distribution', {})
        if sector_dist:
            print("🏭 行业分布:")
            for sector, weight in sector_dist.items():
                print(f"   {sector}: {weight:.1f}%")
    
    return result is not None

def test_position_monitor():
    """测试持仓风险监控"""
    print("\n=== 测试持仓风险监控 ===")
    
    result = test_api_endpoint(
        f"/api/realtime-analysis/risk/position-monitor?portfolio_id={PORTFOLIO_ID}",
        description="持仓风险监控"
    )
    
    if result and result.get('data'):
        data = result['data']
        risk_summary = data.get('risk_summary', {})
        print(f"⚠️ 整体风险等级: {risk_summary.get('overall_risk_level', '未知')}")
        print(f"🔴 高风险持仓: {risk_summary.get('high_risk_positions', 0)}")
        print(f"🟡 中风险持仓: {risk_summary.get('medium_risk_positions', 0)}")
        print(f"📊 风险评分: {risk_summary.get('risk_score', 0)}")
    
    return result is not None

def test_portfolio_risk_calculation():
    """测试投资组合风险计算"""
    print("\n=== 测试投资组合风险计算 ===")
    
    data = {
        "portfolio_id": PORTFOLIO_ID,
        "period_days": 60  # 使用较短的周期进行测试
    }
    
    result = test_api_endpoint(
        "/api/realtime-analysis/risk/portfolio-risk",
        method='POST',
        data=data,
        description="投资组合风险计算"
    )
    
    if result and result.get('data'):
        risk_data = result['data']
        risk_metrics = risk_data.get('risk_metrics', {})
        var_metrics = risk_data.get('var_metrics', {})
        
        print(f"📊 年化收益率: {risk_metrics.get('annual_return', 0):.4f}")
        print(f"📈 年化波动率: {risk_metrics.get('annual_volatility', 0):.4f}")
        print(f"📉 最大回撤: {risk_metrics.get('max_drawdown', 0):.4f}")
        print(f"🎯 夏普比率: {risk_metrics.get('sharpe_ratio', 0):.4f}")
        
        if var_metrics:
            print(f"⚠️ VaR(95%): {var_metrics.get('var_95', 0):.4f}")
            print(f"⚠️ VaR(99%): {var_metrics.get('var_99', 0):.4f}")
    
    return result is not None

def test_stop_loss_take_profit():
    """测试止损止盈管理"""
    print("\n=== 测试止损止盈管理 ===")
    
    data = {
        "portfolio_id": PORTFOLIO_ID,
        "stop_loss_method": "percentage",
        "stop_loss_value": 0.10,  # 10%止损
        "take_profit_method": "percentage", 
        "take_profit_value": 0.20  # 20%止盈
    }
    
    result = test_api_endpoint(
        "/api/realtime-analysis/risk/stop-loss-take-profit",
        method='POST',
        data=data,
        description="止损止盈管理"
    )
    
    if result and result.get('data'):
        data = result['data']
        updated_positions = data.get('updated_positions', [])
        triggered_orders = data.get('triggered_orders', [])
        
        print(f"📝 更新持仓数: {len(updated_positions)}")
        print(f"⚡ 触发订单数: {len(triggered_orders)}")
        
        if updated_positions:
            print("💰 止损止盈设置:")
            for pos in updated_positions[:3]:  # 显示前3个
                print(f"   {pos['ts_code']}: 止损¥{pos['stop_loss_price']:.2f}, 止盈¥{pos['take_profit_price']:.2f}")
    
    return result is not None

def test_risk_alerts():
    """测试风险预警"""
    print("\n=== 测试风险预警 ===")
    
    # 获取现有预警
    result = test_api_endpoint(
        f"/api/realtime-analysis/risk/alerts?portfolio_id={PORTFOLIO_ID}",
        description="获取风险预警"
    )
    
    if result and result.get('data'):
        alerts_data = result['data']
        alerts_by_level = alerts_data.get('alerts_by_level', {})
        
        total_alerts = sum(len(alerts) for alerts in alerts_by_level.values())
        print(f"📢 总预警数: {total_alerts}")
        print(f"🔴 高风险预警: {len(alerts_by_level.get('high', []))}")
        print(f"🟡 中风险预警: {len(alerts_by_level.get('medium', []))}")
        print(f"🟢 低风险预警: {len(alerts_by_level.get('low', []))}")
    
    # 创建测试预警
    alert_data = {
        "ts_code": "000001.SZ",
        "alert_type": "test_alert",
        "alert_level": "medium",
        "alert_message": "测试预警消息",
        "risk_value": 0.15,
        "threshold_value": 0.10
    }
    
    create_result = test_api_endpoint(
        "/api/realtime-analysis/risk/alerts",
        method='POST',
        data=alert_data,
        description="创建测试预警"
    )
    
    return result is not None

def test_stress_test():
    """测试压力测试"""
    print("\n=== 测试压力测试 ===")
    
    data = {
        "portfolio_id": PORTFOLIO_ID
    }
    
    result = test_api_endpoint(
        "/api/realtime-analysis/risk/stress-test",
        method='POST',
        data=data,
        description="压力测试"
    )
    
    if result and result.get('data'):
        stress_data = result['data']
        scenarios = stress_data.get('scenarios', [])
        worst_case = stress_data.get('worst_case', {})
        best_case = stress_data.get('best_case', {})
        
        print(f"🧪 测试场景数: {len(scenarios)}")
        print(f"📉 最坏情况: {worst_case.get('scenario_name', '未知')} ({worst_case.get('pnl_percentage', 0):.2f}%)")
        print(f"📈 最好情况: {best_case.get('scenario_name', '未知')} ({best_case.get('pnl_percentage', 0):.2f}%)")
        
        if scenarios:
            print("📊 压力测试结果:")
            for scenario in scenarios[:3]:  # 显示前3个场景
                print(f"   {scenario['scenario_name']}: {scenario['pnl_percentage']:.2f}%")
    
    return result is not None

def test_batch_update_prices():
    """测试批量更新价格"""
    print("\n=== 测试批量更新价格 ===")
    
    data = {
        "portfolio_id": PORTFOLIO_ID
    }
    
    result = test_api_endpoint(
        "/api/realtime-analysis/risk/batch-update-prices",
        method='POST',
        data=data,
        description="批量更新价格"
    )
    
    if result and result.get('data'):
        data = result['data']
        print(f"📊 总持仓数: {data.get('total_positions', 0)}")
        print(f"✅ 更新成功数: {data.get('updated_positions', 0)}")
    
    return result is not None

def test_risk_thresholds():
    """测试风险阈值管理"""
    print("\n=== 测试风险阈值管理 ===")
    
    # 获取当前阈值
    result = test_api_endpoint(
        "/api/realtime-analysis/risk/risk-thresholds",
        description="获取风险阈值"
    )
    
    if result and result.get('data'):
        thresholds = result['data']
        print("⚙️ 当前风险阈值:")
        for key, value in thresholds.items():
            print(f"   {key}: {value}")
    
    # 更新阈值
    update_data = {
        "position_weight": 0.25,  # 调整单一持仓权重阈值
        "var_limit": 0.06  # 调整VaR限制
    }
    
    update_result = test_api_endpoint(
        "/api/realtime-analysis/risk/risk-thresholds",
        method='PUT',
        data=update_data,
        description="更新风险阈值"
    )
    
    return result is not None

def test_frontend_access():
    """测试前端页面访问"""
    print("\n=== 测试前端页面访问 ===")
    
    try:
        response = requests.get(f"{BASE_URL}/realtime-analysis/risk-management", timeout=10)
        if response.status_code == 200:
            print("✅ 风险管理页面访问: 成功")
            
            # 检查页面关键元素
            content = response.text
            key_elements = [
                "实时风险管理",
                "持仓管理", 
                "风险分析",
                "预警管理",
                "止损止盈",
                "压力测试"
            ]
            
            missing_elements = []
            for element in key_elements:
                if element not in content:
                    missing_elements.append(element)
            
            if missing_elements:
                print(f"⚠️ 缺少页面元素: {', '.join(missing_elements)}")
            else:
                print("✅ 页面元素检查: 完整")
            
            return True
        else:
            print(f"❌ 风险管理页面访问: 失败 (状态码: {response.status_code})")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 风险管理页面访问: 网络错误 - {str(e)}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始风险管理模块测试")
    print(f"📍 测试地址: {BASE_URL}")
    print(f"📁 测试组合: {PORTFOLIO_ID}")
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试项目列表
    tests = [
        ("创建示例投资组合", test_create_sample_portfolio),
        ("投资组合持仓", test_portfolio_positions),
        ("投资组合指标", test_portfolio_metrics),
        ("持仓风险监控", test_position_monitor),
        ("投资组合风险计算", test_portfolio_risk_calculation),
        ("止损止盈管理", test_stop_loss_take_profit),
        ("风险预警", test_risk_alerts),
        ("压力测试", test_stress_test),
        ("批量更新价格", test_batch_update_prices),
        ("风险阈值管理", test_risk_thresholds),
        ("前端页面访问", test_frontend_access)
    ]
    
    # 执行测试
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"🧪 测试: {test_name}")
        print('='*50)
        
        try:
            if test_func():
                passed += 1
            time.sleep(1)  # 避免请求过于频繁
        except Exception as e:
            print(f"❌ 测试异常: {str(e)}")
    
    # 测试总结
    print(f"\n{'='*50}")
    print("📊 测试总结")
    print('='*50)
    print(f"✅ 通过: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"❌ 失败: {total-passed}/{total}")
    
    if passed == total:
        print("🎉 所有测试通过！风险管理模块运行正常。")
    else:
        print("⚠️ 部分测试失败，请检查相关功能。")
    
    print(f"⏰ 测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main() 