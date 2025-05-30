#!/usr/bin/env python3
"""
实时技术指标NaN值修复测试脚本
验证API返回的JSON格式是否正确，前端是否能正常解析
"""

import requests
import json
import sys
from datetime import datetime

def test_indicator_calculation():
    """测试技术指标计算API"""
    print("=" * 60)
    print("实时技术指标NaN值修复测试")
    print("=" * 60)
    
    # 测试配置
    base_url = 'http://127.0.0.1:5001'
    api_url = f'{base_url}/api/realtime-analysis/indicators/calculate'
    
    test_cases = [
        {
            'name': '基础指标测试',
            'data': {
                'ts_code': '000001.SZ',
                'period_type': '5min',
                'indicators': ['MA', 'RSI'],
                'lookback_days': 30
            }
        },
        {
            'name': '复杂指标测试',
            'data': {
                'ts_code': '000001.SZ',
                'period_type': '1min',
                'indicators': ['MACD', 'KDJ', 'BOLL'],
                'lookback_days': 15
            }
        },
        {
            'name': '全指标测试',
            'data': {
                'ts_code': '000002.SZ',
                'period_type': '15min',
                'indicators': ['MA', 'EMA', 'MACD', 'RSI', 'KDJ', 'BOLL', 'CCI', 'WR', 'ATR', 'OBV'],
                'lookback_days': 20
            }
        }
    ]
    
    success_count = 0
    total_tests = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print("-" * 40)
        
        try:
            # 发送API请求
            response = requests.post(api_url, json=test_case['data'], timeout=30)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                # 检查响应是否为有效JSON
                try:
                    json_data = response.json()
                    print("✅ JSON解析成功")
                    
                    # 检查响应结构
                    if 'success' in json_data:
                        if json_data['success']:
                            print("✅ API调用成功")
                            
                            # 检查数据结构
                            if 'data' in json_data:
                                data = json_data['data']
                                print(f"✅ 返回指标数量: {len(data)}")
                                
                                # 检查是否包含NaN值
                                json_str = json.dumps(data)
                                if 'NaN' in json_str or 'nan' in json_str:
                                    print("❌ 检测到NaN值，JSON格式不正确")
                                else:
                                    print("✅ 无NaN值，JSON格式正确")
                                    success_count += 1
                                
                                # 显示部分结果
                                for indicator, result in list(data.items())[:3]:
                                    if isinstance(result, dict) and 'error' not in result:
                                        print(f"   {indicator}: 数据点数量 {len(list(result.values())[0]) if result else 0}")
                                    elif 'error' in result:
                                        print(f"   {indicator}: 错误 - {result['error']}")
                            else:
                                print("❌ 响应中缺少data字段")
                        else:
                            print(f"❌ API调用失败: {json_data.get('message', '未知错误')}")
                    else:
                        print("❌ 响应格式不正确，缺少success字段")
                        
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    print(f"原始响应: {response.text[:200]}...")
                    
            else:
                print(f"❌ HTTP请求失败: {response.status_code}")
                print(f"响应内容: {response.text[:200]}...")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求异常: {e}")
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    # 测试总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"总测试数: {total_tests}")
    print(f"成功数: {success_count}")
    print(f"失败数: {total_tests - success_count}")
    print(f"成功率: {success_count/total_tests*100:.1f}%")
    
    if success_count == total_tests:
        print("🎉 所有测试通过！NaN值修复成功！")
        return True
    else:
        print("⚠️  部分测试失败，需要进一步检查")
        return False

def test_frontend_compatibility():
    """测试前端兼容性"""
    print("\n" + "=" * 60)
    print("前端兼容性测试")
    print("=" * 60)
    
    # 模拟前端JavaScript解析
    test_json = '{"MA10":[null,null,10.5,10.6],"RSI":[null,45.2,55.8,62.1]}'
    
    try:
        # Python解析测试
        data = json.loads(test_json)
        print("✅ Python JSON解析成功")
        
        # 检查null值处理
        ma_values = data.get('MA10', [])
        null_count = ma_values.count(None)
        print(f"✅ MA10数据: {len(ma_values)}个点，{null_count}个null值")
        
        # 模拟前端处理逻辑
        valid_values = [v for v in ma_values if v is not None]
        print(f"✅ 有效数据点: {len(valid_values)}个")
        
        return True
        
    except Exception as e:
        print(f"❌ 前端兼容性测试失败: {e}")
        return False

if __name__ == "__main__":
    print(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 执行测试
    api_test_result = test_indicator_calculation()
    frontend_test_result = test_frontend_compatibility()
    
    # 最终结果
    print("\n" + "=" * 60)
    print("最终测试结果")
    print("=" * 60)
    
    if api_test_result and frontend_test_result:
        print("🎉 所有测试通过！")
        print("✅ NaN值修复成功")
        print("✅ API返回有效JSON")
        print("✅ 前端兼容性良好")
        sys.exit(0)
    else:
        print("❌ 测试失败")
        if not api_test_result:
            print("❌ API测试失败")
        if not frontend_test_result:
            print("❌ 前端兼容性测试失败")
        sys.exit(1) 