#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试前端实时技术指标页面功能
"""

import requests
import json
import time

def test_frontend_indicators():
    """测试前端实时技术指标页面"""
    
    base_url = "http://localhost:5001"
    
    print("🧪 开始测试前端实时技术指标页面...")
    
    # 1. 测试页面是否可访问
    try:
        response = requests.get(f"{base_url}/realtime-analysis/indicators")
        if response.status_code == 200:
            print("✅ 页面访问正常")
        else:
            print(f"❌ 页面访问失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 页面访问异常: {e}")
        return False
    
    # 2. 测试API接口
    try:
        api_url = f"{base_url}/api/realtime-analysis/indicators/calculate"
        test_data = {
            "ts_code": "000001.SZ",
            "period_type": "1min",
            "indicators": ["MA", "RSI", "MACD"],
            "lookback_days": 5
        }
        
        print(f"📡 测试API接口: {api_url}")
        print(f"📤 请求数据: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
        
        response = requests.post(api_url, json=test_data)
        
        print(f"📥 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                print("✅ API响应正常，JSON解析成功")
                
                # 检查响应结构
                if 'success' in result and result['success']:
                    print("✅ API返回成功状态")
                    
                    if 'data' in result:
                        data = result['data']
                        print(f"📊 数据点数量: {data.get('data_points', 'N/A')}")
                        print(f"📈 指标数量: {data.get('total_indicators', 'N/A')}")
                        
                        # 检查是否包含NaN值
                        response_text = response.text
                        if 'NaN' in response_text:
                            print("❌ 响应中仍包含NaN值")
                            return False
                        else:
                            print("✅ 响应中不包含NaN值")
                        
                        # 显示部分指标数据
                        if 'indicators' in data:
                            indicators = data['indicators']
                            print(f"📋 可用指标: {list(indicators.keys())}")
                            
                            for indicator, values in indicators.items():
                                if isinstance(values, list) and len(values) > 0:
                                    print(f"  {indicator}: 前3个值 = {values[:3]}")
                                else:
                                    print(f"  {indicator}: {values}")
                        
                        return True
                    else:
                        print("❌ 响应中缺少data字段")
                        return False
                else:
                    print(f"❌ API返回失败: {result.get('message', '未知错误')}")
                    return False
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"📄 响应内容: {response.text[:500]}...")
                return False
        else:
            print(f"❌ API请求失败，状态码: {response.status_code}")
            print(f"📄 响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ API测试异常: {e}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("🧪 前端实时技术指标页面测试")
    print("=" * 60)
    
    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    time.sleep(3)
    
    success = test_frontend_indicators()
    
    print("=" * 60)
    if success:
        print("🎉 所有测试通过！前端页面功能正常")
    else:
        print("💥 测试失败！需要进一步检查")
    print("=" * 60)

if __name__ == "__main__":
    main() 