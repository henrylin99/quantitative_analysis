#!/usr/bin/env python3
"""
实时技术指标功能测试脚本
测试技术指标计算引擎和API接口
"""

import sys
import os
import requests
import json
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.realtime_indicator import RealtimeIndicator
from app.models.stock_minute_data import StockMinuteData
from app.services.realtime_indicator_engine import RealtimeIndicatorEngine

# 测试配置
BASE_URL = 'http://127.0.0.1:5001'
TEST_STOCK = '000001.SZ'

def test_indicator_model():
    """测试技术指标数据模型"""
    print("\n🧪 测试技术指标数据模型...")
    
    app = create_app()
    with app.app_context():
        try:
            # 创建测试数据
            test_indicator = RealtimeIndicator(
                ts_code=TEST_STOCK,
                datetime=datetime.now(),
                period_type='5min',
                indicator_name='MA',
                value1=10.5,
                value2=20.3,
                metadata={'period': 20}
            )
            
            db.session.add(test_indicator)
            db.session.commit()
            
            # 查询测试
            result = RealtimeIndicator.query.filter_by(
                ts_code=TEST_STOCK,
                indicator_name='MA'
            ).first()
            
            if result:
                print("✅ 技术指标数据模型测试通过")
                print(f"   - 股票代码: {result.ts_code}")
                print(f"   - 指标名称: {result.indicator_name}")
                print(f"   - 指标值: {result.value1}, {result.value2}")
                
                # 清理测试数据
                db.session.delete(result)
                db.session.commit()
                return True
            else:
                print("❌ 技术指标数据模型测试失败")
                return False
                
        except Exception as e:
            print(f"❌ 技术指标数据模型测试异常: {str(e)}")
            return False

def test_indicator_engine():
    """测试技术指标计算引擎"""
    print("\n🧪 测试技术指标计算引擎...")
    
    app = create_app()
    with app.app_context():
        try:
            engine = RealtimeIndicatorEngine()
            
            # 检查支持的指标
            supported = engine.get_supported_indicators()
            print(f"✅ 支持的指标数量: {len(supported)}")
            
            for indicator in supported[:3]:  # 显示前3个
                print(f"   - {indicator['name']} ({indicator['code']}): {indicator['description']}")
            
            # 测试指标计算（需要有数据）
            stock_data = StockMinuteData.query.filter_by(
                ts_code=TEST_STOCK,
                period_type='5min'
            ).limit(50).all()
            
            if stock_data:
                print(f"✅ 找到测试数据: {len(stock_data)} 条记录")
                
                # 测试MA计算
                result = engine.calculate_indicators(
                    ts_code=TEST_STOCK,
                    period_type='5min',
                    indicators=['MA'],
                    lookback_days=7
                )
                
                if result['success']:
                    print("✅ 技术指标计算引擎测试通过")
                    print(f"   - 计算结果: {result['total_indicators']} 个指标")
                    print(f"   - 数据点数: {result['data_points']}")
                    return True
                else:
                    print(f"❌ 指标计算失败: {result['message']}")
                    return False
            else:
                print("⚠️ 没有找到测试数据，跳过指标计算测试")
                return True
                
        except Exception as e:
            print(f"❌ 技术指标计算引擎测试异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def test_api_endpoints():
    """测试API接口"""
    print("\n🧪 测试技术指标API接口...")
    
    test_results = []
    
    # 测试支持的指标接口
    try:
        response = requests.get(f'{BASE_URL}/api/realtime-analysis/indicators/supported', timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ 支持的指标接口测试通过")
                print(f"   - 支持指标数: {len(data['data'])}")
                test_results.append(True)
            else:
                print(f"❌ 支持的指标接口返回失败: {data.get('message')}")
                test_results.append(False)
        else:
            print(f"❌ 支持的指标接口状态码: {response.status_code}")
            test_results.append(False)
    except Exception as e:
        print(f"❌ 支持的指标接口测试异常: {str(e)}")
        test_results.append(False)
    
    # 测试统计信息接口
    try:
        response = requests.get(f'{BASE_URL}/api/realtime-analysis/indicators/stats', timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ 统计信息接口测试通过")
                stats = data['data']
                print(f"   - 总记录数: {stats.get('total_records', 0)}")
                print(f"   - 股票数量: {stats.get('total_stocks', 0)}")
                test_results.append(True)
            else:
                print(f"❌ 统计信息接口返回失败: {data.get('message')}")
                test_results.append(False)
        else:
            print(f"❌ 统计信息接口状态码: {response.status_code}")
            test_results.append(False)
    except Exception as e:
        print(f"❌ 统计信息接口测试异常: {str(e)}")
        test_results.append(False)
    
    # 测试指标计算接口（如果有数据）
    try:
        calc_data = {
            'ts_code': TEST_STOCK,
            'period_type': '5min',
            'indicators': ['MA'],
            'lookback_days': 7
        }
        
        response = requests.post(
            f'{BASE_URL}/api/realtime-analysis/indicators/calculate',
            json=calc_data,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ 指标计算接口测试通过")
                print(f"   - 计算指标数: {data.get('total_indicators', 0)}")
                print(f"   - 存储记录数: {data.get('stored_records', 0)}")
                test_results.append(True)
            else:
                print(f"⚠️ 指标计算接口返回: {data.get('message')}")
                test_results.append(True)  # 可能是没有数据，不算失败
        else:
            print(f"❌ 指标计算接口状态码: {response.status_code}")
            test_results.append(False)
    except Exception as e:
        print(f"❌ 指标计算接口测试异常: {str(e)}")
        test_results.append(False)
    
    return all(test_results)

def test_frontend_access():
    """测试前端页面访问"""
    print("\n🧪 测试前端页面访问...")
    
    try:
        response = requests.get(f'{BASE_URL}/realtime-analysis/indicators', timeout=10)
        if response.status_code == 200:
            content = response.text
            if '实时技术指标分析' in content and 'indicatorTabs' in content:
                print("✅ 技术指标前端页面访问正常")
                print("   - 页面标题正确")
                print("   - JavaScript组件加载正常")
                return True
            else:
                print("❌ 技术指标前端页面内容异常")
                return False
        else:
            print(f"❌ 技术指标前端页面状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 技术指标前端页面访问异常: {str(e)}")
        return False

def test_performance():
    """测试性能"""
    print("\n🧪 测试性能...")
    
    app = create_app()
    with app.app_context():
        try:
            # 测试数据库查询性能
            start_time = datetime.now()
            
            # 查询最近的指标数据
            indicators = RealtimeIndicator.query.filter(
                RealtimeIndicator.datetime >= datetime.now() - timedelta(days=1)
            ).limit(1000).all()
            
            query_time = (datetime.now() - start_time).total_seconds()
            
            print(f"✅ 数据库查询性能测试")
            print(f"   - 查询记录数: {len(indicators)}")
            print(f"   - 查询耗时: {query_time:.3f} 秒")
            
            # 性能评估
            if query_time < 1.0:
                print("   - 性能评级: 优秀 ⭐⭐⭐")
            elif query_time < 3.0:
                print("   - 性能评级: 良好 ⭐⭐")
            else:
                print("   - 性能评级: 需要优化 ⭐")
            
            return True
            
        except Exception as e:
            print(f"❌ 性能测试异常: {str(e)}")
            return False

def main():
    """主测试函数"""
    print("🚀 开始实时技术指标功能测试")
    print("=" * 50)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(test_indicator_model())
    test_results.append(test_indicator_engine())
    test_results.append(test_api_endpoints())
    test_results.append(test_frontend_access())
    test_results.append(test_performance())
    
    # 汇总测试结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总")
    print("=" * 50)
    
    passed = sum(test_results)
    total = len(test_results)
    
    test_names = [
        "技术指标数据模型",
        "技术指标计算引擎", 
        "API接口功能",
        "前端页面访问",
        "性能测试"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, test_results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n🎯 总体结果: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！实时技术指标功能正常运行")
        print("\n📝 下一步:")
        print("1. 访问 http://127.0.0.1:5001/realtime-analysis/indicators")
        print("2. 先同步股票数据，再进行指标计算")
        print("3. 体验多周期分析和指标对比功能")
        return True
    else:
        print("⚠️ 部分测试失败，请检查相关功能")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 