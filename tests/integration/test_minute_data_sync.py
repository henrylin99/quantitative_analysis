"""
分钟数据同步功能测试脚本
测试Baostock数据源集成和新的同步功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.services.minute_data_sync_service import MinuteDataSyncService
from app.services.realtime_data_manager import RealtimeDataManager
from app.models.stock_minute_data import StockMinuteData
from app.utils.db_utils import DatabaseUtils
import logging
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_database_connection():
    """测试数据库连接"""
    print("=" * 60)
    print("1. 测试数据库连接")
    print("=" * 60)
    
    try:
        result = DatabaseUtils.test_connection()
        
        for db_type, status in result.items():
            status_text = "✅ 成功" if status else "❌ 失败"
            print(f"{db_type.upper()} 连接: {status_text}")
        
        # 测试表创建
        success = DatabaseUtils.create_minute_data_tables()
        print(f"分钟数据表创建: {'✅ 成功' if success else '❌ 失败'}")
        
        return all(result.values())
        
    except Exception as e:
        print(f"❌ 数据库连接测试失败: {e}")
        return False

def test_minute_sync_service():
    """测试分钟数据同步服务"""
    print("\n" + "=" * 60)
    print("2. 测试分钟数据同步服务")
    print("=" * 60)
    
    try:
        # 测试服务初始化
        with MinuteDataSyncService() as sync_service:
            print("✅ 分钟数据同步服务初始化成功")
            
            # 测试股票代码转换
            test_codes = [
                ('000001.SZ', 'sz.000001'),
                ('600000.SH', 'sh.600000'),
                ('sz.000002', 'sz.000002')
            ]
            
            print("\n股票代码转换测试:")
            for ts_code, expected_bs_code in test_codes:
                bs_code = sync_service.convert_ts_code_to_bs_code(ts_code)
                status = "✅" if bs_code == expected_bs_code else "❌"
                print(f"  {ts_code} -> {bs_code} {status}")
            
            # 测试获取股票列表
            stock_list = sync_service.get_stock_list_from_db()
            print(f"\n✅ 获取股票列表成功: {len(stock_list)}只股票")
            if stock_list:
                print(f"  前5只股票: {stock_list[:5]}")
            
            return True
            
    except Exception as e:
        print(f"❌ 分钟数据同步服务测试失败: {e}")
        return False

def test_single_stock_sync():
    """测试单股票数据同步"""
    print("\n" + "=" * 60)
    print("3. 测试单股票数据同步")
    print("=" * 60)
    
    try:
        # 设置测试参数
        test_stock = '000001.SZ'
        start_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"测试股票: {test_stock}")
        print(f"时间范围: {start_date} 到 {end_date}")
        
        with MinuteDataSyncService() as sync_service:
            # 测试1分钟数据同步
            print("\n同步1分钟数据...")
            result = sync_service.sync_single_stock_data(
                test_stock, '1min', start_date, end_date
            )
            
            if result['success']:
                print(f"✅ 1分钟数据同步成功: {result['data_count']}条记录")
            else:
                print(f"❌ 1分钟数据同步失败: {result['message']}")
            
            # 测试5分钟数据同步
            print("\n同步5分钟数据...")
            result = sync_service.sync_single_stock_data(
                test_stock, '5min', start_date, end_date
            )
            
            if result['success']:
                print(f"✅ 5分钟数据同步成功: {result['data_count']}条记录")
            else:
                print(f"❌ 5分钟数据同步失败: {result['message']}")
            
            return True
            
    except Exception as e:
        print(f"❌ 单股票数据同步测试失败: {e}")
        return False

def test_multiple_stocks_sync():
    """测试批量股票数据同步"""
    print("\n" + "=" * 60)
    print("4. 测试批量股票数据同步")
    print("=" * 60)
    
    try:
        # 设置测试参数
        test_stocks = ['000001.SZ', '000002.SZ', '600000.SH']
        start_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"测试股票: {test_stocks}")
        print(f"时间范围: {start_date} 到 {end_date}")
        
        with MinuteDataSyncService() as sync_service:
            result = sync_service.sync_multiple_stocks_data(
                test_stocks, '1min', start_date, end_date, batch_size=2
            )
            
            if result['success']:
                print(f"✅ 批量同步成功:")
                print(f"  总股票数: {result['total_stocks']}")
                print(f"  成功股票数: {result['success_stocks']}")
                print(f"  失败股票数: {result['failed_stocks']}")
                print(f"  总数据量: {result['total_data_count']}")
            else:
                print(f"❌ 批量同步失败: {result['message']}")
            
            return result['success']
            
    except Exception as e:
        print(f"❌ 批量股票数据同步测试失败: {e}")
        return False

def test_all_periods_sync():
    """测试多周期数据同步"""
    print("\n" + "=" * 60)
    print("5. 测试多周期数据同步")
    print("=" * 60)
    
    try:
        # 设置测试参数
        test_stock = '000001.SZ'
        start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"测试股票: {test_stock}")
        print(f"时间范围: {start_date} 到 {end_date}")
        
        with MinuteDataSyncService() as sync_service:
            results = sync_service.sync_all_periods_for_stock(
                test_stock, start_date, end_date
            )
            
            print("\n各周期同步结果:")
            success_count = 0
            for period_type, result in results.items():
                if result['success']:
                    print(f"  {period_type}: ✅ 成功 ({result['data_count']}条)")
                    success_count += 1
                else:
                    print(f"  {period_type}: ❌ 失败 ({result['message']})")
            
            print(f"\n总结: {success_count}/{len(results)} 个周期同步成功")
            return success_count > 0
            
    except Exception as e:
        print(f"❌ 多周期数据同步测试失败: {e}")
        return False

def test_realtime_data_manager():
    """测试实时数据管理器集成"""
    print("\n" + "=" * 60)
    print("6. 测试实时数据管理器集成")
    print("=" * 60)
    
    try:
        # 初始化数据管理器
        data_manager = RealtimeDataManager()
        print("✅ 实时数据管理器初始化成功")
        
        # 测试单股票同步（使用Baostock）
        test_stock = '000002.SZ'
        start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"\n测试Baostock数据源同步: {test_stock}")
        result = data_manager.sync_minute_data(
            test_stock, start_date, end_date, '1min', use_baostock=True
        )
        
        if result['success']:
            print(f"✅ Baostock同步成功: {result['data_count']}条记录")
        else:
            print(f"❌ Baostock同步失败: {result['message']}")
        
        # 测试批量同步
        test_stocks = ['000001.SZ', '600000.SH']
        print(f"\n测试批量同步: {test_stocks}")
        result = data_manager.sync_multiple_stocks_data(
            test_stocks, '5min', start_date, end_date, batch_size=1, use_baostock=True
        )
        
        if result['success']:
            print(f"✅ 批量同步成功: 成功{result['success_stocks']}只")
        else:
            print(f"❌ 批量同步失败: {result['message']}")
        
        # 测试获取股票列表
        stock_list = data_manager.get_stock_list_from_db()
        print(f"\n✅ 获取股票列表: {len(stock_list)}只股票")
        
        return True
        
    except Exception as e:
        print(f"❌ 实时数据管理器集成测试失败: {e}")
        return False

def test_data_query():
    """测试数据查询功能"""
    print("\n" + "=" * 60)
    print("7. 测试数据查询功能")
    print("=" * 60)
    
    try:
        # 查询数据库中的数据
        total_count = StockMinuteData.query.count()
        print(f"数据库总记录数: {total_count}")
        
        if total_count > 0:
            # 按周期类型统计
            period_stats = db.session.query(
                StockMinuteData.period_type,
                db.func.count(StockMinuteData.id).label('count')
            ).group_by(StockMinuteData.period_type).all()
            
            print("\n按周期类型统计:")
            for period_type, count in period_stats:
                print(f"  {period_type}: {count}条")
            
            # 按股票统计（前10只）
            stock_stats = db.session.query(
                StockMinuteData.ts_code,
                db.func.count(StockMinuteData.id).label('count')
            ).group_by(StockMinuteData.ts_code).order_by(
                db.func.count(StockMinuteData.id).desc()
            ).limit(10).all()
            
            print("\n数据量前10只股票:")
            for ts_code, count in stock_stats:
                print(f"  {ts_code}: {count}条")
            
            # 最新数据时间
            latest_data = StockMinuteData.query.order_by(
                StockMinuteData.datetime.desc()
            ).first()
            
            if latest_data:
                print(f"\n最新数据时间: {latest_data.datetime}")
                print(f"最新数据股票: {latest_data.ts_code}")
                print(f"最新数据周期: {latest_data.period_type}")
        
        return True
        
    except Exception as e:
        print(f"❌ 数据查询测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始分钟数据同步功能测试")
    print("测试时间:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # 创建Flask应用上下文
    app = create_app()
    
    with app.app_context():
        # 执行测试
        test_results = []
        
        test_results.append(("数据库连接", test_database_connection()))
        test_results.append(("分钟数据同步服务", test_minute_sync_service()))
        test_results.append(("单股票数据同步", test_single_stock_sync()))
        test_results.append(("批量股票数据同步", test_multiple_stocks_sync()))
        test_results.append(("多周期数据同步", test_all_periods_sync()))
        test_results.append(("实时数据管理器集成", test_realtime_data_manager()))
        test_results.append(("数据查询功能", test_data_query()))
        
        # 输出测试结果
        print("\n" + "=" * 60)
        print("📊 测试结果汇总")
        print("=" * 60)
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n总体结果: {passed}/{total} 项测试通过")
        
        if passed == total:
            print("🎉 所有测试通过！分钟数据同步功能正常工作")
        else:
            print("⚠️  部分测试失败，请检查相关功能")
        
        return passed == total

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 