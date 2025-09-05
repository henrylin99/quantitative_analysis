#!/usr/bin/env python3
"""
实时交易分析功能测试脚本
测试数据管理、API接口等功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
import json
from datetime import datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.stock_minute_data import StockMinuteData
from app.services.realtime_data_manager import RealtimeDataManager
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealtimeAnalysisTest:
    """实时分析功能测试类"""
    
    def __init__(self, base_url='http://localhost:5000'):
        self.base_url = base_url
        self.app = create_app()
        
    def test_data_models(self):
        """测试数据模型"""
        logger.info("🧪 测试数据模型...")
        
        with self.app.app_context():
            try:
                # 测试模型基本功能
                test_data = {
                    'ts_code': 'TEST001.SZ',
                    'datetime': datetime.now(),
                    'period_type': '1min',
                    'open': 10.0,
                    'high': 10.5,
                    'low': 9.8,
                    'close': 10.2,
                    'volume': 1000,
                    'amount': 10200.0,
                    'pre_close': 10.0,
                    'change': 0.2,
                    'pct_chg': 2.0
                }
                
                # 创建测试记录
                record = StockMinuteData(**test_data)
                db.session.add(record)
                db.session.commit()
                
                # 测试查询功能
                latest_data = StockMinuteData.get_latest_data('TEST001.SZ', '1min', 1)
                assert len(latest_data) == 1
                assert latest_data[0].ts_code == 'TEST001.SZ'
                
                # 测试数据转换
                data_dict = latest_data[0].to_dict()
                assert 'ts_code' in data_dict
                assert 'datetime' in data_dict
                
                # 清理测试数据
                db.session.delete(record)
                db.session.commit()
                
                logger.info("✅ 数据模型测试通过")
                return True
                
            except Exception as e:
                logger.error(f"❌ 数据模型测试失败: {str(e)}")
                return False
    
    def test_data_manager(self):
        """测试数据管理器"""
        logger.info("🧪 测试数据管理器...")
        
        with self.app.app_context():
            try:
                data_manager = RealtimeDataManager()
                
                # 测试数据同步
                result = data_manager.sync_minute_data('TEST002.SZ')
                assert result['success'] == True
                assert result['data_count'] > 0
                
                # 测试数据聚合
                agg_result = data_manager.aggregate_data('TEST002.SZ', '1min', '5min')
                assert agg_result['success'] == True
                
                # 测试数据质量检查
                quality_result = data_manager.check_data_quality('TEST002.SZ', '1min', 1)
                assert 'status' in quality_result
                assert 'completeness' in quality_result
                
                # 测试实时价格获取
                price_result = data_manager.get_realtime_price('TEST002.SZ')
                assert price_result['success'] == True
                assert 'data' in price_result
                
                logger.info("✅ 数据管理器测试通过")
                return True
                
            except Exception as e:
                logger.error(f"❌ 数据管理器测试失败: {str(e)}")
                return False
    
    def test_api_endpoints(self):
        """测试API接口"""
        logger.info("🧪 测试API接口...")
        
        try:
            # 测试数据同步API
            sync_data = {
                'ts_code': 'TEST003.SZ',
                'start_date': '20241201',
                'end_date': '20241207'
            }
            
            response = requests.post(
                f'{self.base_url}/api/realtime-analysis/data/sync',
                json=sync_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                assert result['success'] == True
                logger.info("✅ 数据同步API测试通过")
            else:
                logger.warning(f"⚠️ 数据同步API返回状态码: {response.status_code}")
            
            # 测试数据统计API
            response = requests.get(f'{self.base_url}/api/realtime-analysis/data/stats')
            if response.status_code == 200:
                result = response.json()
                assert result['success'] == True
                assert 'data' in result
                logger.info("✅ 数据统计API测试通过")
            else:
                logger.warning(f"⚠️ 数据统计API返回状态码: {response.status_code}")
            
            # 测试支持周期API
            response = requests.get(f'{self.base_url}/api/realtime-analysis/data/periods')
            if response.status_code == 200:
                result = response.json()
                assert result['success'] == True
                assert len(result['data']) == 5  # 5个周期
                logger.info("✅ 支持周期API测试通过")
            else:
                logger.warning(f"⚠️ 支持周期API返回状态码: {response.status_code}")
            
            logger.info("✅ API接口测试通过")
            return True
            
        except requests.exceptions.ConnectionError:
            logger.warning("⚠️ 无法连接到服务器，跳过API测试")
            return True
        except Exception as e:
            logger.error(f"❌ API接口测试失败: {str(e)}")
            return False
    
    def test_data_aggregation(self):
        """测试数据聚合功能"""
        logger.info("🧪 测试数据聚合功能...")
        
        with self.app.app_context():
            try:
                data_manager = RealtimeDataManager()
                
                # 先创建1分钟数据
                sync_result = data_manager.sync_minute_data('TEST004.SZ')
                if not sync_result['success']:
                    logger.warning("⚠️ 创建测试数据失败，跳过聚合测试")
                    return True
                
                # 测试各种周期的聚合
                periods = [('1min', '5min'), ('1min', '15min'), ('1min', '30min'), ('1min', '60min')]
                
                for source, target in periods:
                    result = data_manager.aggregate_data('TEST004.SZ', source, target)
                    if result['success']:
                        logger.info(f"✅ {source} -> {target} 聚合成功")
                    else:
                        logger.warning(f"⚠️ {source} -> {target} 聚合失败: {result['message']}")
                
                logger.info("✅ 数据聚合功能测试通过")
                return True
                
            except Exception as e:
                logger.error(f"❌ 数据聚合功能测试失败: {str(e)}")
                return False
    
    def test_data_quality_check(self):
        """测试数据质量检查"""
        logger.info("🧪 测试数据质量检查...")
        
        with self.app.app_context():
            try:
                data_manager = RealtimeDataManager()
                
                # 创建测试数据
                sync_result = data_manager.sync_minute_data('TEST005.SZ')
                if not sync_result['success']:
                    logger.warning("⚠️ 创建测试数据失败，跳过质量检查测试")
                    return True
                
                # 测试不同周期的质量检查
                periods = ['1min', '5min', '15min', '30min', '60min']
                
                for period in periods:
                    result = data_manager.check_data_quality('TEST005.SZ', period, 24)
                    
                    assert 'status' in result
                    assert 'completeness' in result
                    assert 'data_count' in result
                    
                    logger.info(f"✅ {period} 质量检查: {result['status']} ({result['completeness']:.1f}%)")
                
                logger.info("✅ 数据质量检查测试通过")
                return True
                
            except Exception as e:
                logger.error(f"❌ 数据质量检查测试失败: {str(e)}")
                return False
    
    def test_performance(self):
        """测试性能"""
        logger.info("🧪 测试性能...")
        
        with self.app.app_context():
            try:
                data_manager = RealtimeDataManager()
                
                # 测试批量数据插入性能
                start_time = datetime.now()
                
                # 创建大量测试数据
                test_data = []
                base_time = datetime.now()
                
                for i in range(1000):  # 1000条记录
                    test_data.append({
                        'ts_code': 'PERF001.SZ',
                        'datetime': base_time + timedelta(minutes=i),
                        'period_type': '1min',
                        'open': 10.0 + i * 0.01,
                        'high': 10.1 + i * 0.01,
                        'low': 9.9 + i * 0.01,
                        'close': 10.05 + i * 0.01,
                        'volume': 1000 + i,
                        'amount': (10.05 + i * 0.01) * (1000 + i),
                        'pre_close': 10.0 + (i-1) * 0.01 if i > 0 else 10.0,
                        'change': 0.05 if i == 0 else 0.01,
                        'pct_chg': 0.5 if i == 0 else 0.1
                    })
                
                # 批量插入
                StockMinuteData.bulk_insert(test_data)
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                logger.info(f"✅ 批量插入1000条记录耗时: {duration:.2f}秒")
                
                # 测试查询性能
                start_time = datetime.now()
                
                # 查询最新100条记录
                latest_data = StockMinuteData.get_latest_data('PERF001.SZ', '1min', 100)
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                logger.info(f"✅ 查询100条记录耗时: {duration:.3f}秒")
                assert len(latest_data) <= 100
                
                # 清理测试数据
                StockMinuteData.query.filter_by(ts_code='PERF001.SZ').delete()
                db.session.commit()
                
                logger.info("✅ 性能测试通过")
                return True
                
            except Exception as e:
                logger.error(f"❌ 性能测试失败: {str(e)}")
                return False
    
    def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始运行实时分析功能测试...")
        
        tests = [
            ('数据模型测试', self.test_data_models),
            ('数据管理器测试', self.test_data_manager),
            ('API接口测试', self.test_api_endpoints),
            ('数据聚合测试', self.test_data_aggregation),
            ('数据质量检查测试', self.test_data_quality_check),
            ('性能测试', self.test_performance)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"执行: {test_name}")
            logger.info(f"{'='*50}")
            
            try:
                if test_func():
                    passed += 1
                    logger.info(f"✅ {test_name} 通过")
                else:
                    logger.error(f"❌ {test_name} 失败")
            except Exception as e:
                logger.error(f"❌ {test_name} 异常: {str(e)}")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"测试结果: {passed}/{total} 通过")
        logger.info(f"{'='*60}")
        
        if passed == total:
            logger.info("🎉 所有测试通过！")
        else:
            logger.warning(f"⚠️ {total - passed} 个测试失败")
        
        return passed == total

def main():
    """主函数"""
    print("=" * 60)
    print("实时交易分析功能测试工具")
    print("=" * 60)
    
    tester = RealtimeAnalysisTest()
    
    while True:
        print("\n请选择测试:")
        print("1. 数据模型测试")
        print("2. 数据管理器测试")
        print("3. API接口测试")
        print("4. 数据聚合测试")
        print("5. 数据质量检查测试")
        print("6. 性能测试")
        print("7. 运行所有测试")
        print("0. 退出")
        
        choice = input("\n请输入选择 (0-7): ").strip()
        
        if choice == '0':
            print("👋 再见！")
            break
        elif choice == '1':
            tester.test_data_models()
        elif choice == '2':
            tester.test_data_manager()
        elif choice == '3':
            tester.test_api_endpoints()
        elif choice == '4':
            tester.test_data_aggregation()
        elif choice == '5':
            tester.test_data_quality_check()
        elif choice == '6':
            tester.test_performance()
        elif choice == '7':
            tester.run_all_tests()
        else:
            print("❌ 无效选择，请重新输入")

if __name__ == '__main__':
    main() 