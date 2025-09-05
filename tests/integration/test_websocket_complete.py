#!/usr/bin/env python3
"""
完整的WebSocket功能测试脚本
测试WebSocket连接、推送服务、API接口等功能
"""

import requests
import json
import time
import socketio
from datetime import datetime

def test_websocket_complete():
    """完整测试WebSocket功能"""
    base_url = "http://127.0.0.1:5001"
    
    print("🧪 开始完整测试WebSocket功能...")
    print("=" * 60)
    
    test_results = []
    
    # 1. 测试WebSocket API接口
    print("📋 测试 1: WebSocket API接口")
    
    # 1.1 获取WebSocket状态
    try:
        response = requests.get(f"{base_url}/api/websocket/status")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ WebSocket状态获取成功: {data['data']['is_running']}")
            test_results.append(("WebSocket状态获取", "PASS", None))
        else:
            print(f"❌ WebSocket状态获取失败: {response.status_code}")
            test_results.append(("WebSocket状态获取", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ WebSocket状态获取异常: {e}")
        test_results.append(("WebSocket状态获取", "FAIL", str(e)))
    
    # 1.2 获取连接统计
    try:
        response = requests.get(f"{base_url}/api/websocket/connections")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 连接统计获取成功: {data['data']}")
            test_results.append(("连接统计获取", "PASS", None))
        else:
            print(f"❌ 连接统计获取失败: {response.status_code}")
            test_results.append(("连接统计获取", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 连接统计获取异常: {e}")
        test_results.append(("连接统计获取", "FAIL", str(e)))
    
    # 1.3 获取推送配置
    try:
        response = requests.get(f"{base_url}/api/websocket/push-config")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 推送配置获取成功: {len(data['data'])} 个配置项")
            test_results.append(("推送配置获取", "PASS", None))
        else:
            print(f"❌ 推送配置获取失败: {response.status_code}")
            test_results.append(("推送配置获取", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 推送配置获取异常: {e}")
        test_results.append(("推送配置获取", "FAIL", str(e)))
    
    # 1.4 获取支持的推送类型
    try:
        response = requests.get(f"{base_url}/api/websocket/supported-types")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 支持的推送类型获取成功: {len(data['data'])} 种类型")
            test_results.append(("支持的推送类型获取", "PASS", None))
        else:
            print(f"❌ 支持的推送类型获取失败: {response.status_code}")
            test_results.append(("支持的推送类型获取", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 支持的推送类型获取异常: {e}")
        test_results.append(("支持的推送类型获取", "FAIL", str(e)))
    
    # 2. 测试推送服务控制
    print(f"\n📋 测试 2: 推送服务控制")
    
    # 2.1 启动推送服务
    try:
        response = requests.post(f"{base_url}/api/websocket/start")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 推送服务启动成功: {data['message']}")
            test_results.append(("推送服务启动", "PASS", None))
        else:
            print(f"❌ 推送服务启动失败: {response.status_code}")
            test_results.append(("推送服务启动", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 推送服务启动异常: {e}")
        test_results.append(("推送服务启动", "FAIL", str(e)))
    
    # 等待服务启动
    time.sleep(2)
    
    # 2.2 测试连接
    try:
        response = requests.post(f"{base_url}/api/websocket/test-connection")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 连接测试成功: {data['message']}")
            test_results.append(("连接测试", "PASS", None))
        else:
            print(f"❌ 连接测试失败: {response.status_code}")
            test_results.append(("连接测试", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 连接测试异常: {e}")
        test_results.append(("连接测试", "FAIL", str(e)))
    
    # 3. 测试推送配置更新
    print(f"\n📋 测试 3: 推送配置更新")
    
    try:
        config_data = {
            "market_data": {
                "enabled": True,
                "interval": 30
            },
            "indicators": {
                "enabled": True,
                "interval": 60
            }
        }
        
        response = requests.put(
            f"{base_url}/api/websocket/push-config",
            json=config_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 推送配置更新成功")
            test_results.append(("推送配置更新", "PASS", None))
        else:
            print(f"❌ 推送配置更新失败: {response.status_code}")
            test_results.append(("推送配置更新", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 推送配置更新异常: {e}")
        test_results.append(("推送配置更新", "FAIL", str(e)))
    
    # 4. 测试立即推送
    print(f"\n📋 测试 4: 立即推送")
    
    try:
        push_data = {
            "type": "market_data",
            "data": {
                "ts_code": "000001.SZ",
                "datetime": datetime.now().isoformat(),
                "close": 10.50,
                "change_pct": 2.5
            }
        }
        
        response = requests.post(
            f"{base_url}/api/websocket/push",
            json=push_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 立即推送成功: {data['message']}")
            test_results.append(("立即推送", "PASS", None))
        else:
            print(f"❌ 立即推送失败: {response.status_code}")
            test_results.append(("立即推送", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 立即推送异常: {e}")
        test_results.append(("立即推送", "FAIL", str(e)))
    
    # 5. 测试WebSocket客户端连接
    print(f"\n📋 测试 5: WebSocket客户端连接")
    
    try:
        # 创建SocketIO客户端
        sio = socketio.SimpleClient()
        
        # 连接到服务器
        sio.connect(f"{base_url}")
        print("✅ WebSocket客户端连接成功")
        
        # 发送心跳测试
        sio.emit('ping')
        print("✅ 心跳测试发送成功")
        
        # 订阅市场数据
        sio.emit('subscribe', {
            'type': 'market_data',
            'params': {'symbol': '000001.SZ'}
        })
        print("✅ 市场数据订阅成功")
        
        # 等待一段时间接收消息
        time.sleep(3)
        
        # 断开连接
        sio.disconnect()
        print("✅ WebSocket客户端断开成功")
        
        test_results.append(("WebSocket客户端连接", "PASS", None))
        
    except Exception as e:
        print(f"❌ WebSocket客户端连接异常: {e}")
        test_results.append(("WebSocket客户端连接", "FAIL", str(e)))
    
    # 6. 测试页面访问
    print(f"\n📋 测试 6: 页面访问")
    
    try:
        response = requests.get(f"{base_url}/realtime-analysis/websocket-management")
        if response.status_code == 200:
            print("✅ WebSocket管理页面访问成功")
            test_results.append(("WebSocket管理页面访问", "PASS", None))
        else:
            print(f"❌ WebSocket管理页面访问失败: {response.status_code}")
            test_results.append(("WebSocket管理页面访问", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ WebSocket管理页面访问异常: {e}")
        test_results.append(("WebSocket管理页面访问", "FAIL", str(e)))
    
    # 7. 停止推送服务
    print(f"\n📋 测试 7: 停止推送服务")
    
    try:
        response = requests.post(f"{base_url}/api/websocket/stop")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 推送服务停止成功: {data['message']}")
            test_results.append(("推送服务停止", "PASS", None))
        else:
            print(f"❌ 推送服务停止失败: {response.status_code}")
            test_results.append(("推送服务停止", "FAIL", f"状态码: {response.status_code}"))
    except Exception as e:
        print(f"❌ 推送服务停止异常: {e}")
        test_results.append(("推送服务停止", "FAIL", str(e)))
    
    # 输出测试结果汇总
    print(f"\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result, error in test_results:
        status_icon = "✅" if result == "PASS" else "❌"
        print(f"{status_icon} {test_name}: {result}")
        if error:
            print(f"   错误信息: {error}")
        
        if result == "PASS":
            passed += 1
        else:
            failed += 1
    
    print(f"\n📈 测试统计:")
    print(f"   总测试数: {len(test_results)}")
    print(f"   通过数: {passed}")
    print(f"   失败数: {failed}")
    print(f"   通过率: {passed/len(test_results)*100:.1f}%")
    
    if failed == 0:
        print(f"\n🎉 所有测试通过！WebSocket功能正常运行。")
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，请检查相关功能。")

if __name__ == "__main__":
    test_websocket_complete() 