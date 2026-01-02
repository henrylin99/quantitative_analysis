#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库查看工具
专注于查看表结构和数据内容，不进行复杂计算
"""

import pymysql
import pandas as pd
from datetime import datetime

class DatabaseViewer:
    """数据库查看器"""
    
    def __init__(self, host='localhost', user='root', password='root', 
                 database='stock_cursor', charset='utf8mb4'):
        """初始化数据库连接"""
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.connection = None
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor
            )
            print(f"✅ 成功连接到数据库: {self.database}")
            return True
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            print("🔒 数据库连接已关闭")
    
    def show_tables(self):
        """显示所有表"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                
            print("\n📊 数据库表列表:")
            print("=" * 50)
            for i, table in enumerate(tables, 1):
                table_name = list(table.values())[0]
                print(f"{i:2d}. {table_name}")
            
            return [list(table.values())[0] for table in tables]
            
        except Exception as e:
            print(f"❌ 获取表列表失败: {e}")
            return None
    
    def describe_table(self, table_name):
        """查看表结构"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"DESCRIBE {table_name}")
                columns = cursor.fetchall()
                
                # 获取表注释
                cursor.execute(f"""
                    SELECT TABLE_COMMENT 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = '{self.database}' 
                    AND TABLE_NAME = '{table_name}'
                """)
                table_comment = cursor.fetchone()
                
            print(f"\n📋 表结构: {table_name}")
            if table_comment and table_comment['TABLE_COMMENT']:
                print(f"📝 表说明: {table_comment['TABLE_COMMENT']}")
            print("=" * 80)
            
            print(f"{'字段名':<20} {'类型':<15} {'是否为空':<8} {'键':<8} {'默认值':<10} {'备注'}")
            print("-" * 80)
            
            for col in columns:
                field = col['Field']
                type_info = col['Type']
                null_info = col['Null']
                key_info = col['Key']
                default_info = str(col['Default']) if col['Default'] is not None else 'NULL'
                extra_info = col['Extra']
                
                print(f"{field:<20} {type_info:<15} {null_info:<8} {key_info:<8} {default_info:<10} {extra_info}")
            
            return columns
            
        except Exception as e:
            print(f"❌ 查看表结构失败: {e}")
            return None
    
    def get_table_stats(self, table_name):
        """获取表的统计信息"""
        try:
            with self.connection.cursor() as cursor:
                # 获取行数
                cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
                row_count = cursor.fetchone()['row_count']
                
                # 获取表大小
                cursor.execute(f"""
                    SELECT 
                        ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                    FROM information_schema.tables 
                    WHERE table_schema = '{self.database}' 
                    AND table_name = '{table_name}'
                """)
                size_info = cursor.fetchone()
                
            print(f"\n📈 表 {table_name} 统计信息:")
            print("=" * 40)
            print(f"📊 总行数: {row_count:,}")
            print(f"💾 表大小: {size_info['size_mb']} MB")
            
            return {
                'row_count': row_count,
                'size_mb': size_info['size_mb']
            }
            
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return None
    
    def show_sample_data(self, table_name, limit=5):
        """显示样本数据"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
                rows = cursor.fetchall()
                
            if not rows:
                print(f"\n❌ 表 {table_name} 中没有数据")
                return None
                
            print(f"\n📊 表 {table_name} 样本数据 (前{limit}行):")
            print("=" * 100)
            
            # 获取列名
            columns = list(rows[0].keys())
            
            # 打印表头
            header = " | ".join([f"{col[:15]:<15}" for col in columns])
            print(header)
            print("-" * len(header))
            
            # 打印数据行
            for row in rows:
                row_data = " | ".join([f"{str(row[col])[:15]:<15}" for col in columns])
                print(row_data)
            
            return rows
            
        except Exception as e:
            print(f"❌ 获取样本数据失败: {e}")
            return None
    
    def check_stock_data(self, ts_code="000001.SZ"):
        """检查特定股票的数据"""
        print(f"\n🔍 检查股票 {ts_code} 的数据...")
        
        # 检查基本信息
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM stock_basic WHERE ts_code = '{ts_code}'")
                basic_info = cursor.fetchone()
                
            if basic_info:
                print(f"\n📋 股票基本信息:")
                print(f"  股票代码: {basic_info['ts_code']}")
                print(f"  股票名称: {basic_info['name']}")
                print(f"  所属行业: {basic_info['industry']}")
                print(f"  所属地区: {basic_info['area']}")
                print(f"  上市日期: {basic_info['list_date']}")
            else:
                print(f"❌ 未找到股票 {ts_code} 的基本信息")
                return
                
        except Exception as e:
            print(f"❌ 查询股票基本信息失败: {e}")
            return
        
        # 检查各表的数据量
        tables_to_check = [
            'stock_daily_history',
            'stock_daily_basic', 
            'stock_factor',
            'stock_moneyflow',
            'stock_income_statement',
            'stock_balance_sheet',
            'stock_cash_flow'
        ]
        
        print(f"\n📊 股票 {ts_code} 各表数据统计:")
        print("-" * 50)
        
        for table in tables_to_check:
            try:
                with self.connection.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*) as count FROM {table} WHERE ts_code = '{ts_code}'")
                    count = cursor.fetchone()['count']
                    print(f"{table:<25}: {count:>8,} 条记录")
                    
            except Exception as e:
                print(f"{table:<25}: 查询失败 ({e})")
    
    def show_recent_data(self, ts_code="000001.SZ", table_name="stock_daily_history", limit=10):
        """显示最近的数据"""
        print(f"\n📊 股票 {ts_code} 在表 {table_name} 中的最新数据:")
        
        try:
            with self.connection.cursor() as cursor:
                # 尝试按trade_date排序
                cursor.execute(f"""
                    SELECT * FROM {table_name} 
                    WHERE ts_code = '{ts_code}' 
                    ORDER BY trade_date DESC 
                    LIMIT {limit}
                """)
                rows = cursor.fetchall()
                
            if not rows:
                print(f"❌ 未找到股票 {ts_code} 在表 {table_name} 中的数据")
                return None
                
            print("=" * 120)
            
            # 获取列名
            columns = list(rows[0].keys())
            
            # 打印表头
            header = " | ".join([f"{col[:12]:<12}" for col in columns])
            print(header)
            print("-" * len(header))
            
            # 打印数据行
            for row in rows:
                row_data = " | ".join([f"{str(row[col])[:12]:<12}" for col in columns])
                print(row_data)
            
            return rows
            
        except Exception as e:
            print(f"❌ 获取最新数据失败: {e}")
            return None
    
    def run_custom_query(self, query):
        """运行自定义SQL查询"""
        print(f"\n🔍 执行自定义查询:")
        print(f"SQL: {query}")
        print("=" * 80)
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                
            if not rows:
                print("❌ 查询结果为空")
                return None
                
            # 获取列名
            columns = list(rows[0].keys())
            
            # 打印表头
            header = " | ".join([f"{col[:15]:<15}" for col in columns])
            print(header)
            print("-" * len(header))
            
            # 打印数据行（最多显示20行）
            for i, row in enumerate(rows[:20]):
                row_data = " | ".join([f"{str(row[col])[:15]:<15}" for col in columns])
                print(row_data)
                
            if len(rows) > 20:
                print(f"... 还有 {len(rows) - 20} 行数据未显示")
                
            print(f"\n📊 查询结果: 共 {len(rows)} 行")
            
            return rows
            
        except Exception as e:
            print(f"❌ 查询执行失败: {e}")
            return None

def main():
    """主函数"""
    print("🚀 数据库查看工具")
    print("=" * 60)
    
    # 初始化查看器
    viewer = DatabaseViewer()
    
    if not viewer.connect():
        return
    
    try:
        # 1. 显示所有表
        tables = viewer.show_tables()
        
        # 2. 查看重要表的结构
        important_tables = ['stock_basic', 'stock_daily_history', 'stock_factor']
        
        for table in important_tables:
            if table in tables:
                print(f"\n{'='*60}")
                viewer.describe_table(table)
                viewer.get_table_stats(table)
                viewer.show_sample_data(table, 3)
        
        # 3. 检查特定股票数据
        test_stock = "000001.SZ"
        viewer.check_stock_data(test_stock)
        
        # 4. 显示最新数据
        viewer.show_recent_data(test_stock, "stock_daily_history", 5)
        
        # 5. 运行一些有用的查询
        print(f"\n{'='*60}")
        print("🔍 运行一些有用的查询示例:")
        
        # 查询股票数量
        viewer.run_custom_query("SELECT COUNT(DISTINCT ts_code) as stock_count FROM stock_basic")
        
        # 查询数据日期范围
        viewer.run_custom_query("""
            SELECT 
                MIN(trade_date) as earliest_date,
                MAX(trade_date) as latest_date,
                COUNT(DISTINCT trade_date) as trading_days
            FROM stock_daily_history
        """)
        
        print("\n✅ 数据库查看完成!")
        print("\n💡 使用建议:")
        print("1. 根据查看结果，确认数据库中有足够的数据进行因子计算")
        print("2. 可以修改 test_stock 变量查看其他股票的数据")
        print("3. 可以使用 run_custom_query() 方法执行自定义SQL查询")
        print("4. 确认数据质量后，可以运行因子计算工具")
        
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        
    finally:
        viewer.close()

if __name__ == "__main__":
    main() 