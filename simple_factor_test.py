#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的因子测试脚本
测试基本的数据库访问和简单因子计算
"""

import pymysql
import pandas as pd
import numpy as np
from datetime import datetime

class SimpleFactorTest:
    """简化的因子测试类"""
    
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
    
    def check_data_availability(self, ts_code="000001.SZ"):
        """检查数据可用性"""
        print(f"\n🔍 检查股票 {ts_code} 的数据可用性...")
        
        tables_to_check = [
            'stock_basic',
            'stock_daily_history', 
            'stock_daily_basic',
            'stock_factor',
            'stock_moneyflow'
        ]
        
        data_summary = {}
        
        for table in tables_to_check:
            try:
                query = f"SELECT COUNT(*) as count FROM {table} WHERE ts_code = '{ts_code}'"
                with self.connection.cursor() as cursor:
                    cursor.execute(query)
                    result = cursor.fetchone()
                    count = result['count']
                    data_summary[table] = count
                    print(f"📋 {table}: {count:,} 条记录")
                    
            except Exception as e:
                print(f"❌ 检查表 {table} 失败: {e}")
                data_summary[table] = 0
        
        return data_summary
    
    def get_latest_data(self, ts_code="000001.SZ", limit=5):
        """获取最新数据"""
        print(f"\n📊 获取股票 {ts_code} 的最新数据...")
        
        try:
            query = f"""
            SELECT 
                trade_date,
                close,
                pct_chg,
                vol,
                amount
            FROM stock_daily_history 
            WHERE ts_code = '{ts_code}'
            ORDER BY trade_date DESC 
            LIMIT {limit}
            """
            
            df = pd.read_sql(query, self.connection)
            
            if not df.empty:
                print("📈 最新行情数据:")
                print(df.to_string(index=False))
                return df
            else:
                print("❌ 未找到数据")
                return None
                
        except Exception as e:
            print(f"❌ 获取最新数据失败: {e}")
            return None
    
    def calculate_simple_factors(self, ts_code="000001.SZ", days=30):
        """计算简单因子"""
        print(f"\n🧮 计算股票 {ts_code} 的简单因子 (最近{days}天)...")
        
        try:
            query = f"""
            SELECT 
                trade_date,
                close,
                pct_chg,
                vol,
                amount,
                LAG(close, 1) OVER (ORDER BY trade_date) as prev_close,
                LAG(close, 5) OVER (ORDER BY trade_date) as close_5d_ago,
                LAG(close, 10) OVER (ORDER BY trade_date) as close_10d_ago
            FROM stock_daily_history 
            WHERE ts_code = '{ts_code}'
            ORDER BY trade_date DESC 
            LIMIT {days}
            """
            
            df = pd.read_sql(query, self.connection)
            
            if df.empty:
                print("❌ 未找到数据")
                return None
            
            # 计算简单因子
            df = df.sort_values('trade_date')  # 按时间正序排列
            
            # 1. 价格动量因子
            df['momentum_5d'] = ((df['close'] / df['close_5d_ago']) - 1) * 100
            df['momentum_10d'] = ((df['close'] / df['close_10d_ago']) - 1) * 100
            
            # 2. 移动平均
            df['ma5'] = df['close'].rolling(5).mean()
            df['ma10'] = df['close'].rolling(10).mean()
            
            # 3. 价格相对位置
            df['price_position'] = (df['close'] - df['close'].rolling(20).min()) / (df['close'].rolling(20).max() - df['close'].rolling(20).min())
            
            # 4. 成交量比率
            df['volume_ratio'] = df['vol'] / df['vol'].rolling(10).mean()
            
            # 5. 波动率
            df['volatility'] = df['pct_chg'].rolling(10).std()
            
            print("✅ 因子计算完成!")
            print("\n📊 因子数据样本 (最近5天):")
            
            factor_cols = ['trade_date', 'close', 'momentum_5d', 'momentum_10d', 'volume_ratio', 'volatility']
            print(df[factor_cols].tail().to_string(index=False))
            
            return df
            
        except Exception as e:
            print(f"❌ 计算简单因子失败: {e}")
            return None
    
    def analyze_factor_distribution(self, factor_data, factor_name='momentum_5d'):
        """分析因子分布"""
        if factor_data is None or factor_data.empty:
            print("❌ 无数据可分析")
            return
        
        print(f"\n📈 因子 {factor_name} 分布分析:")
        print("=" * 40)
        
        factor_values = factor_data[factor_name].dropna()
        
        if len(factor_values) == 0:
            print("❌ 因子数据为空")
            return
        
        print(f"📊 样本数量: {len(factor_values)}")
        print(f"📊 均值: {factor_values.mean():.4f}")
        print(f"📊 标准差: {factor_values.std():.4f}")
        print(f"📊 最小值: {factor_values.min():.4f}")
        print(f"📊 最大值: {factor_values.max():.4f}")
        print(f"📊 中位数: {factor_values.median():.4f}")
        
        # 分位数
        quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]
        print("\n📊 分位数分布:")
        for q in quantiles:
            value = factor_values.quantile(q)
            print(f"  {q*100:4.0f}%: {value:8.4f}")

def main():
    """主函数"""
    print("🚀 简化因子测试工具")
    print("=" * 60)
    
    # 初始化测试工具
    tester = SimpleFactorTest()
    
    if not tester.connect():
        return
    
    try:
        # 1. 显示表列表
        tables = tester.show_tables()
        
        # 2. 检查数据可用性
        test_stock = "000001.SZ"
        data_summary = tester.check_data_availability(test_stock)
        
        # 3. 获取最新数据
        latest_data = tester.get_latest_data(test_stock)
        
        # 4. 计算简单因子
        if data_summary.get('stock_daily_history', 0) > 0:
            factor_data = tester.calculate_simple_factors(test_stock, days=60)
            
            # 5. 分析因子分布
            if factor_data is not None:
                tester.analyze_factor_distribution(factor_data, 'momentum_5d')
                tester.analyze_factor_distribution(factor_data, 'volume_ratio')
        
        print("\n✅ 测试完成!")
        print("\n💡 建议:")
        print("1. 如果数据充足，可以尝试运行完整的因子计算工具")
        print("2. 可以修改 test_stock 变量测试其他股票")
        print("3. 可以调整 days 参数获取更多历史数据")
        
    except Exception as e:
        print(f"❌ 测试过程出错: {e}")
        
    finally:
        tester.close()

if __name__ == "__main__":
    main() 