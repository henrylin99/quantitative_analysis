#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速财务因子测试脚本
用于测试数据类型转换和因子计算修复
"""

import pymysql
import pandas as pd
import numpy as np

def quick_test():
    """快速测试数据库连接和数据类型"""
    print("🧪 快速财务因子测试")
    print("=" * 50)
    
    try:
        # 连接数据库
        connection = pymysql.connect(
            host='localhost',
            user='root',
            password='root',
            database='stock_cursor',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print("✅ 数据库连接成功")
        
        # 简单查询测试
        query = """
        SELECT 
            i.ts_code,
            i.end_date,
            i.revenue,
            i.oper_cost,
            i.operate_profit,
            i.n_income_attr_p,
            b.total_assets,
            b.total_cur_assets,
            b.total_cur_liab,
            c.n_cashflow_act
        FROM stock_income_statement i
        LEFT JOIN stock_balance_sheet b ON i.ts_code = b.ts_code AND i.end_date = b.end_date
        LEFT JOIN stock_cash_flow c ON i.ts_code = c.ts_code AND i.end_date = c.end_date
        WHERE i.ts_code = '000001.SZ' 
        AND i.end_date >= '2022-12-31'
        ORDER BY i.end_date
        LIMIT 5
        """
        
        df = pd.read_sql(query, connection)
        print(f"📊 获取数据条数: {len(df)}")
        
        print("\n🔍 原始数据类型:")
        for col in ['revenue', 'oper_cost', 'operate_profit', 'total_assets']:
            if col in df.columns:
                print(f"  {col}: {df[col].dtype} - 样本值: {df[col].iloc[0] if len(df) > 0 else 'N/A'}")
        
        # 转换数据类型
        numeric_cols = ['revenue', 'oper_cost', 'operate_profit', 'n_income_attr_p', 
                       'total_assets', 'total_cur_assets', 'total_cur_liab', 'n_cashflow_act']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df[numeric_cols] = df[numeric_cols].fillna(0)
        
        print("\n🔄 转换后数据类型:")
        for col in ['revenue', 'oper_cost', 'operate_profit', 'total_assets']:
            if col in df.columns:
                print(f"  {col}: {df[col].dtype} - 样本值: {df[col].iloc[0] if len(df) > 0 else 'N/A'}")
        
        # 测试因子计算
        print("\n🧮 测试因子计算:")
        if len(df) > 0:
            # 安全除法函数
            def safe_divide(num, den, default=0):
                return np.where(den != 0, num / den, default)
            
            # 计算毛利率
            df['gross_margin'] = safe_divide(df['revenue'] - df['oper_cost'], df['revenue']) * 100
            
            # 计算营业利润率
            df['operating_margin'] = safe_divide(df['operate_profit'], df['revenue']) * 100
            
            # 计算流动比率
            df['current_ratio'] = safe_divide(df['total_cur_assets'], df['total_cur_liab'])
            
            print(f"  毛利率: {df['gross_margin'].iloc[0]:.2f}%")
            print(f"  营业利润率: {df['operating_margin'].iloc[0]:.2f}%")
            print(f"  流动比率: {df['current_ratio'].iloc[0]:.2f}")
            
            print("\n✅ 因子计算成功！数据类型转换正常")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_enhanced_factors():
    """测试增强版财务因子工具"""
    print("\n🚀 测试增强版财务因子工具")
    print("=" * 50)
    
    try:
        from enhanced_financial_factors import EnhancedFinancialFactors
        
        # 初始化
        calculator = EnhancedFinancialFactors()
        
        # 测试单个股票
        result = calculator.generate_financial_report(
            ts_code="000001.SZ",
            start_date="2022-12-31",
            end_date="2023-12-31"
        )
        
        if result is not None and len(result) > 0:
            print("✅ 增强版工具测试成功！")
            
            # 显示计算出的因子数量
            factor_cols = [col for col in result.columns 
                          if col not in ['ts_code', 'end_date', 'ann_date', 'f_ann_date', 'report_type']]
            numeric_factors = [col for col in factor_cols 
                             if result[col].dtype in ['float64', 'int64']]
            
            print(f"📊 数据记录数: {len(result)}")
            print(f"🧮 数值型因子数: {len(numeric_factors)}")
            
            # 显示几个关键因子的值
            if len(result) > 0:
                latest = result.iloc[-1]
                key_factors = ['gross_profit_margin', 'net_profit_margin', 'current_ratio']
                
                print("\n📋 关键因子示例:")
                for factor in key_factors:
                    if factor in result.columns:
                        value = latest[factor]
                        if pd.notna(value):
                            print(f"  {factor}: {value:.4f}")
                        else:
                            print(f"  {factor}: N/A")
        else:
            print("❌ 增强版工具测试失败")
            
        calculator.close()
        
    except Exception as e:
        print(f"❌ 增强版工具测试出错: {e}")

if __name__ == "__main__":
    print("🏃 开始快速财务因子测试")
    print("=" * 70)
    
    # 1. 基础连接和数据类型测试
    basic_success = quick_test()
    
    # 2. 增强版工具测试
    if basic_success:
        test_enhanced_factors()
    
    print("\n🎉 测试完成！") 