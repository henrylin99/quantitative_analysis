#!/usr/bin/env python3
"""
实时监控功能测试脚本
测试实时监控服务的各项功能
"""

import requests
import json
import time
from datetime import datetime

# 测试配置
BASE_URL = "http://127.0.0.1:5001"
API_BASE = f"{BASE_URL}/api/realtime-analysis/monitor"

def test_monitor_overview():
    """测试监控概览"""
    print("🔍 测试监控概览...")
    try:
        response = requests.get(f"{API_BASE}/overview")
        data = response.json()
        
        if data.get('success'):
            overview = data.get('data', {})
            print(f"   ✅ 总股票数: {overview.get('total_stocks', 0)}")
            print(f"   ✅ 活跃股票: {overview.get('active_stocks', 0)}")
            print(f"   ✅ 今日数据量: {overview.get('today_records', 0)}")
            print(f"   ✅ 数据延迟: {overview.get('data_delay', 0)}分钟")
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_realtime_quotes():
    """测试实时行情"""
    print("📊 测试实时行情...")
    try:
        # 测试默认行情
        response = requests.get(f"{API_BASE}/quotes?limit=10")
        data = response.json()
        
        if data.get('success'):
            quotes = data.get('data', {}).get('quotes', [])
            print(f"   ✅ 获取到 {len(quotes)} 只股票的行情数据")
            
            if quotes:
                quote = quotes[0]
                print(f"   📈 示例: {quote.get('name')} ({quote.get('ts_code')})")
                print(f"      价格: ¥{quote.get('current_price', 0):.2f}")
                print(f"      涨跌幅: {quote.get('change_pct', 0):.2f}%")
                print(f"      成交量: {quote.get('volume', 0):,.0f}")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_sector_performance():
    """测试板块表现"""
    print("🏢 测试板块表现...")
    try:
        response = requests.get(f"{API_BASE}/sectors?period_hours=1")
        data = response.json()
        
        if data.get('success'):
            sectors = data.get('data', {}).get('sectors', [])
            print(f"   ✅ 获取到 {len(sectors)} 个板块的表现数据")
            
            if sectors:
                # 显示前3个板块
                for i, sector in enumerate(sectors[:3]):
                    print(f"   {i+1}. {sector.get('sector_name')}: {sector.get('avg_change_pct', 0):.2f}%")
                    print(f"      上涨比例: {sector.get('rising_ratio', 0):.1f}%")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_anomaly_detection():
    """测试异动检测"""
    print("⚡ 测试异动检测...")
    try:
        response = requests.get(f"{API_BASE}/anomalies?change_threshold=3.0&volume_threshold=2.0")
        data = response.json()
        
        if data.get('success'):
            anomalies = data.get('data', {}).get('anomalies', [])
            print(f"   ✅ 检测到 {len(anomalies)} 只异动股票")
            
            if anomalies:
                anomaly = anomalies[0]
                print(f"   🚨 异动示例: {anomaly.get('name')} ({anomaly.get('ts_code')})")
                print(f"      涨跌幅: {anomaly.get('change_pct', 0):.2f}%")
                print(f"      异动类型: {', '.join(anomaly.get('anomaly_types', []))}")
                print(f"      异动评分: {anomaly.get('anomaly_score', 0):.1f}")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_market_sentiment():
    """测试市场情绪"""
    print("💭 测试市场情绪...")
    try:
        response = requests.get(f"{API_BASE}/sentiment?period_hours=1")
        data = response.json()
        
        if data.get('success'):
            sentiment = data.get('data', {})
            print(f"   ✅ 情绪评分: {sentiment.get('sentiment_score', 0):.1f}")
            print(f"   ✅ 市场状态: {sentiment.get('market_status', '未知')}")
            print(f"   ✅ 上涨股票: {sentiment.get('rising_stocks', 0)}")
            print(f"   ✅ 下跌股票: {sentiment.get('falling_stocks', 0)}")
            print(f"   ✅ 上涨比例: {sentiment.get('rising_ratio', 0):.1f}%")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_top_movers():
    """测试涨跌幅排行"""
    print("🏆 测试涨跌幅排行...")
    try:
        response = requests.get(f"{API_BASE}/top-movers?limit=5")
        data = response.json()
        
        if data.get('success'):
            movers = data.get('data', {})
            gainers = movers.get('top_gainers', [])
            losers = movers.get('top_losers', [])
            active = movers.get('most_active', [])
            
            print(f"   ✅ 涨幅榜: {len(gainers)} 只股票")
            print(f"   ✅ 跌幅榜: {len(losers)} 只股票")
            print(f"   ✅ 活跃榜: {len(active)} 只股票")
            
            if gainers:
                gainer = gainers[0]
                print(f"   📈 涨幅第一: {gainer.get('name')} +{gainer.get('change_pct', 0):.2f}%")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_market_heatmap():
    """测试市场热力图"""
    print("🗺️ 测试市场热力图...")
    try:
        response = requests.get(f"{API_BASE}/heatmap?period_hours=1")
        data = response.json()
        
        if data.get('success'):
            heatmap = data.get('data', {}).get('heatmap', [])
            print(f"   ✅ 热力图数据: {len(heatmap)} 个板块")
            
            if heatmap:
                # 显示前3个板块的热力图数据
                for i, item in enumerate(heatmap[:3]):
                    print(f"   {i+1}. {item.get('name')}: {item.get('value', 0):.2f}%")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_price_alerts():
    """测试价格预警"""
    print("🚨 测试价格预警...")
    try:
        response = requests.get(f"{API_BASE}/alerts?change_threshold=2.0&volume_threshold=1.5")
        data = response.json()
        
        if data.get('success'):
            alerts = data.get('data', {}).get('alerts', [])
            print(f"   ✅ 价格预警: {len(alerts)} 个")
            
            if alerts:
                alert = alerts[0]
                print(f"   🔔 预警示例: {alert.get('name')}")
                print(f"      预警类型: {alert.get('alert_type')}")
                print(f"      严重程度: {alert.get('severity')}")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_market_stats():
    """测试市场统计"""
    print("📊 测试市场统计...")
    try:
        response = requests.get(f"{API_BASE}/market-stats?period_hours=1")
        data = response.json()
        
        if data.get('success'):
            stats = data.get('data', {})
            sentiment = stats.get('market_sentiment', {})
            stock_stats = stats.get('stock_stats', {})
            trading_stats = stats.get('trading_stats', {})
            
            print(f"   ✅ 市场情绪评分: {sentiment.get('score', 0):.1f}")
            print(f"   ✅ 市场状态: {sentiment.get('status', '未知')}")
            print(f"   ✅ 总股票数: {stock_stats.get('total_stocks', 0)}")
            print(f"   ✅ 异动股票数: {stats.get('anomaly_count', 0)}")
            print(f"   ✅ 平均涨跌幅: {trading_stats.get('avg_change_pct', 0):.2f}%")
            
            return True
        else:
            print(f"   ❌ 失败: {data.get('message')}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def test_frontend_access():
    """测试前端页面访问"""
    print("🌐 测试前端页面访问...")
    try:
        # 测试实时监控页面
        response = requests.get(f"{BASE_URL}/realtime-analysis/monitor")
        
        if response.status_code == 200:
            print("   ✅ 实时监控页面访问正常")
            
            # 检查页面内容
            content = response.text
            if "实时监控面板" in content:
                print("   ✅ 页面标题正确")
            if "实时行情" in content:
                print("   ✅ 实时行情模块存在")
            if "板块表现" in content:
                print("   ✅ 板块表现模块存在")
            if "异动股票" in content:
                print("   ✅ 异动股票模块存在")
            if "市场情绪" in content:
                print("   ✅ 市场情绪模块存在")
            
            return True
        else:
            print(f"   ❌ 页面访问失败，状态码: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ 错误: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 实时监控功能测试")
    print("=" * 60)
    
    test_results = []
    
    # API接口测试
    print("\n📡 API接口测试")
    print("-" * 40)
    test_results.append(("监控概览", test_monitor_overview()))
    test_results.append(("实时行情", test_realtime_quotes()))
    test_results.append(("板块表现", test_sector_performance()))
    test_results.append(("异动检测", test_anomaly_detection()))
    test_results.append(("市场情绪", test_market_sentiment()))
    test_results.append(("涨跌幅排行", test_top_movers()))
    test_results.append(("市场热力图", test_market_heatmap()))
    test_results.append(("价格预警", test_price_alerts()))
    test_results.append(("市场统计", test_market_stats()))
    
    # 前端页面测试
    print("\n🌐 前端页面测试")
    print("-" * 40)
    test_results.append(("前端页面访问", test_frontend_access()))
    
    # 测试结果汇总
    print("\n" + "=" * 60)
    print("📋 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:<15} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"测试通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有测试通过！实时监控功能正常运行")
    else:
        print("⚠️  部分测试失败，请检查相关功能")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 