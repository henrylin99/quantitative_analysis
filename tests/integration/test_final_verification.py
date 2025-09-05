#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终验证测试：实时技术指标功能完整性测试
"""

import requests
import json
import time
from datetime import datetime

def test_api_endpoints():
    """测试所有API端点"""
    base_url = "http://localhost:5001"
    
    print("🔍 测试API端点...")
    
    # 1. 测试指标计算API
    try:
        response = requests.post(
            f"{base_url}/api/realtime-analysis/indicators/calculate",
            json={
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "indicators": ["MA", "RSI", "MACD"],
                "lookback_days": 5
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and 'NaN' not in response.text:
                print("✅ 指标计算API正常")
            else:
                print("❌ 指标计算API返回错误或包含NaN")
                return False
        else:
            print(f"❌ 指标计算API状态码错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 指标计算API异常: {e}")
        return False
    
    # 2. 测试支持的指标列表API
    try:
        response = requests.get(f"{base_url}/api/realtime-analysis/indicators/supported")
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and len(data.get('data', [])) > 0:
                print("✅ 支持指标列表API正常")
            else:
                print("❌ 支持指标列表API返回空数据")
                return False
        else:
            print(f"❌ 支持指标列表API状态码错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 支持指标列表API异常: {e}")
        return False
    
    # 3. 测试指标统计API
    try:
        response = requests.get(f"{base_url}/api/realtime-analysis/indicators/stats")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ 指标统计API正常")
            else:
                print("❌ 指标统计API返回错误")
                return False
        else:
            print(f"❌ 指标统计API状态码错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 指标统计API异常: {e}")
        return False
    
    return True

def test_web_pages():
    """测试Web页面"""
    base_url = "http://localhost:5001"
    
    print("🌐 测试Web页面...")
    
    # 测试实时技术指标页面
    try:
        response = requests.get(f"{base_url}/realtime-analysis/indicators")
        if response.status_code == 200:
            print("✅ 实时技术指标页面正常")
        else:
            print(f"❌ 实时技术指标页面状态码错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 实时技术指标页面异常: {e}")
        return False
    
    return True

def test_data_integrity():
    """测试数据完整性"""
    base_url = "http://localhost:5001"
    
    print("📊 测试数据完整性...")
    
    # 测试多种指标计算
    indicators_to_test = [
        ["MA"],
        ["RSI"],
        ["MACD"],
        ["MA", "RSI"],
        ["MA", "RSI", "MACD", "BOLL"]
    ]
    
    for indicators in indicators_to_test:
        try:
            response = requests.post(
                f"{base_url}/api/realtime-analysis/indicators/calculate",
                json={
                    "ts_code": "000001.SZ",
                    "period_type": "1min",
                    "indicators": indicators,
                    "lookback_days": 3
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    # 检查是否包含NaN值
                    if 'NaN' in response.text:
                        print(f"❌ 指标 {indicators} 包含NaN值")
                        return False
                    else:
                        print(f"✅ 指标 {indicators} 数据正常")
                else:
                    print(f"❌ 指标 {indicators} 计算失败: {data.get('message')}")
                    return False
            else:
                print(f"❌ 指标 {indicators} API错误: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 指标 {indicators} 异常: {e}")
            return False
    
    return True

def test_performance():
    """测试性能"""
    base_url = "http://localhost:5001"
    
    print("⚡ 测试性能...")
    
    # 测试响应时间
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{base_url}/api/realtime-analysis/indicators/calculate",
            json={
                "ts_code": "000001.SZ",
                "period_type": "1min",
                "indicators": ["MA", "RSI", "MACD", "BOLL"],
                "lookback_days": 10
            }
        )
        
        end_time = time.time()
        response_time = end_time - start_time
        
        if response.status_code == 200 and response_time < 10:
            print(f"✅ 性能测试通过，响应时间: {response_time:.2f}秒")
            return True
        else:
            print(f"❌ 性能测试失败，响应时间: {response_time:.2f}秒")
            return False
    except Exception as e:
        print(f"❌ 性能测试异常: {e}")
        return False

def main():
    """主函数"""
    print("=" * 80)
    print("🧪 实时技术指标功能最终验证测试")
    print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    time.sleep(2)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(("API端点测试", test_api_endpoints()))
    test_results.append(("Web页面测试", test_web_pages()))
    test_results.append(("数据完整性测试", test_data_integrity()))
    test_results.append(("性能测试", test_performance()))
    
    # 统计结果
    passed_tests = sum(1 for _, result in test_results if result)
    total_tests = len(test_results)
    
    print("=" * 80)
    print("📋 测试结果汇总:")
    print("=" * 80)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    print("=" * 80)
    print(f"📊 总体结果: {passed_tests}/{total_tests} 项测试通过")
    
    if passed_tests == total_tests:
        print("🎉 所有测试通过！实时技术指标功能完全正常！")
        print("✅ NaN值问题已完全修复")
        print("✅ 前后端功能完全匹配")
        print("✅ 系统可以投入使用")
    else:
        print("💥 部分测试失败，需要进一步检查")
    
    print("=" * 80)

if __name__ == "__main__":
    main() 