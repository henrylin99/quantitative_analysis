#!/usr/bin/env python3
"""
交易信号功能测试脚本
测试信号生成、融合、查询和管理功能
"""

import sys
import os
import requests
import json
import time
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试配置
BASE_URL = 'http://127.0.0.1:5001'
TEST_STOCK = '000001.SZ'

def test_api_endpoint(method, endpoint, data=None, params=None):
    """测试API接口"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method.upper() == 'GET':
            response = requests.get(url, params=params, timeout=30)
        elif method.upper() == 'POST':
            response = requests.post(url, json=data, timeout=30)
        else:
            return False, f"不支持的HTTP方法: {method}"
        
        if response.status_code == 200:
            result = response.json()
            return True, result
        else:
            return False, f"HTTP错误: {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        return False, f"请求异常: {str(e)}"
    except json.JSONDecodeError as e:
        return False, f"JSON解析错误: {str(e)}"

def test_signal_generation():
    """测试信号生成功能"""
    print("\n🧪 测试信号生成功能...")
    
    # 测试数据
    test_data = {
        'ts_code': TEST_STOCK,
        'period_type': '1min',
        'strategies': ['ma_crossover', 'rsi_divergence', 'macd_signal'],
        'lookback_days': 5
    }
    
    success, result = test_api_endpoint('POST', '/api/realtime-analysis/signals/generate', test_data)
    
    if success:
        if result.get('success'):
            signals_count = result.get('data', {}).get('signals_generated', 0)
            print(f"✅ 信号生成成功，生成了 {signals_count} 个信号")
            return True
        else:
            print(f"❌ 信号生成失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def test_signal_fusion():
    """测试信号融合功能"""
    print("\n🧪 测试信号融合功能...")
    
    # 测试数据
    test_data = {
        'ts_code': TEST_STOCK,
        'period_type': '1min',
        'time_window_hours': 1
    }
    
    success, result = test_api_endpoint('POST', '/api/realtime-analysis/signals/fuse', test_data)
    
    if success:
        if result.get('success'):
            fused_signal = result.get('data', {}).get('fused_signal', 'UNKNOWN')
            contributing_signals = result.get('data', {}).get('contributing_signals', 0)
            print(f"✅ 信号融合成功，融合信号: {fused_signal}，参与信号数: {contributing_signals}")
            return True
        else:
            print(f"❌ 信号融合失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def test_active_signals():
    """测试活跃信号查询"""
    print("\n🧪 测试活跃信号查询...")
    
    params = {
        'ts_code': TEST_STOCK,
        'limit': 10
    }
    
    success, result = test_api_endpoint('GET', '/api/realtime-analysis/signals/active', params=params)
    
    if success:
        if result.get('success'):
            signals_count = len(result.get('data', []))
            print(f"✅ 活跃信号查询成功，找到 {signals_count} 个活跃信号")
            return True
        else:
            print(f"❌ 活跃信号查询失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def test_supported_strategies():
    """测试支持的策略列表"""
    print("\n🧪 测试支持的策略列表...")
    
    success, result = test_api_endpoint('GET', '/api/realtime-analysis/signals/strategies')
    
    if success:
        if result.get('success'):
            strategies_count = len(result.get('data', []))
            print(f"✅ 策略列表查询成功，支持 {strategies_count} 种策略")
            
            # 显示策略详情
            for strategy in result.get('data', [])[:3]:  # 只显示前3个
                print(f"   - {strategy.get('display_name')}: {strategy.get('description')}")
            
            return True
        else:
            print(f"❌ 策略列表查询失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def test_signal_stats():
    """测试信号统计信息"""
    print("\n🧪 测试信号统计信息...")
    
    success, result = test_api_endpoint('GET', '/api/realtime-analysis/signals/stats')
    
    if success:
        if result.get('success'):
            stats = result.get('data', {})
            total_signals = stats.get('total_signals', 0)
            total_stocks = stats.get('total_stocks', 0)
            print(f"✅ 信号统计查询成功，总信号数: {total_signals}，涉及股票数: {total_stocks}")
            return True
        else:
            print(f"❌ 信号统计查询失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def test_strategy_backtest():
    """测试策略回测功能"""
    print("\n🧪 测试策略回测功能...")
    
    # 计算测试日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    test_data = {
        'strategy_name': 'ma_crossover',
        'ts_code': TEST_STOCK,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'period_type': '1min'
    }
    
    success, result = test_api_endpoint('POST', '/api/realtime-analysis/signals/backtest', test_data)
    
    if success:
        if result.get('success'):
            backtest_data = result.get('data', {})
            total_return = backtest_data.get('total_return', 0)
            data_points = backtest_data.get('data_points', 0)
            print(f"✅ 策略回测成功，总收益率: {total_return:.2f}%，数据点数: {data_points}")
            return True
        else:
            print(f"❌ 策略回测失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def test_frontend_access():
    """测试前端页面访问"""
    print("\n🧪 测试前端页面访问...")
    
    pages = [
        ('/realtime-analysis/signals', '交易信号页面'),
        ('/realtime-analysis', '实时分析主页')
    ]
    
    success_count = 0
    
    for url, name in pages:
        try:
            response = requests.get(f"{BASE_URL}{url}", timeout=10)
            if response.status_code == 200:
                print(f"✅ {name} 访问成功")
                success_count += 1
            else:
                print(f"❌ {name} 访问失败: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ {name} 访问异常: {str(e)}")
    
    return success_count == len(pages)

def test_batch_operations():
    """测试批量操作"""
    print("\n🧪 测试批量操作...")
    
    # 批量生成信号
    test_data = {
        'stock_codes': [TEST_STOCK, '000002.SZ'],
        'period_type': '5min',
        'strategies': ['rsi_divergence', 'macd_signal'],
        'lookback_days': 3
    }
    
    success, result = test_api_endpoint('POST', '/api/realtime-analysis/signals/batch-generate', test_data)
    
    if success:
        if result.get('success'):
            summary = result.get('summary', {})
            total_stocks = summary.get('total_stocks', 0)
            success_count = summary.get('success', 0)
            total_signals = summary.get('total_signals_generated', 0)
            print(f"✅ 批量生成信号成功，处理股票数: {total_stocks}，成功数: {success_count}，总信号数: {total_signals}")
            return True
        else:
            print(f"❌ 批量生成信号失败: {result.get('message', '未知错误')}")
            return False
    else:
        print(f"❌ API调用失败: {result}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("🚀 开始交易信号功能测试...")
    print(f"📊 测试目标: {BASE_URL}")
    print(f"📈 测试股票: {TEST_STOCK}")
    
    # 测试项目列表
    tests = [
        ("支持的策略列表", test_supported_strategies),
        ("信号生成功能", test_signal_generation),
        ("信号融合功能", test_signal_fusion),
        ("活跃信号查询", test_active_signals),
        ("信号统计信息", test_signal_stats),
        ("策略回测功能", test_strategy_backtest),
        ("批量操作功能", test_batch_operations),
        ("前端页面访问", test_frontend_access)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"🧪 测试项目: {test_name}")
        print(f"{'='*50}")
        
        try:
            result = test_func()
            results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
                
        except Exception as e:
            print(f"💥 {test_name} 测试异常: {str(e)}")
            results.append((test_name, False))
        
        # 测试间隔
        time.sleep(1)
    
    # 输出测试总结
    print(f"\n{'='*60}")
    print("📊 测试总结")
    print(f"{'='*60}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"总测试数: {total}")
    print(f"通过数量: {passed}")
    print(f"失败数量: {total - passed}")
    print(f"通过率: {passed/total*100:.1f}%")
    
    print(f"\n📋 详细结果:")
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} {test_name}")
    
    if passed == total:
        print(f"\n🎉 所有测试通过！交易信号功能正常运行。")
        return True
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查相关功能。")
        return False

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1) 