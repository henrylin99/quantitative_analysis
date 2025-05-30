#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查因子数据的日期范围
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorValues
from sqlalchemy import text

def check_factor_dates():
    """检查因子数据的日期范围"""
    app = create_app()
    
    with app.app_context():
        print("📅 检查因子数据的日期范围")
        print("=" * 60)
        
        try:
            # 检查所有因子的日期范围
            result = db.session.execute(text('''
                SELECT 
                    factor_id,
                    COUNT(*) as count,
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date,
                    COUNT(DISTINCT ts_code) as stock_count
                FROM factor_values 
                GROUP BY factor_id 
                ORDER BY factor_id
            '''))
            
            factors = result.fetchall()
            print("📊 因子数据详情:")
            for factor_id, count, min_date, max_date, stock_count in factors:
                print(f"   📈 {factor_id}:")
                print(f"      记录数: {count}")
                print(f"      日期范围: {min_date} 至 {max_date}")
                print(f"      股票数量: {stock_count}")
                print()
            
            # 检查2023年的数据
            print("🔍 检查2023年的数据:")
            result_2023 = db.session.execute(text('''
                SELECT 
                    factor_id,
                    COUNT(*) as count
                FROM factor_values 
                WHERE trade_date >= '2023-01-01' AND trade_date <= '2023-12-31'
                GROUP BY factor_id 
                ORDER BY factor_id
            '''))
            
            factors_2023 = result_2023.fetchall()
            for factor_id, count in factors_2023:
                print(f"   📊 {factor_id}: {count} 条记录 (2023年)")
            
            if not factors_2023:
                print("   ❌ 2023年没有因子数据")
                
                # 检查最近的数据
                print("\n🔍 检查最近的数据:")
                result_recent = db.session.execute(text('''
                    SELECT 
                        factor_id,
                        trade_date,
                        COUNT(*) as count
                    FROM factor_values 
                    GROUP BY factor_id, trade_date
                    ORDER BY trade_date DESC
                    LIMIT 10
                '''))
                
                recent_data = result_recent.fetchall()
                for factor_id, trade_date, count in recent_data:
                    print(f"   📅 {trade_date}: {factor_id} ({count} 条记录)")
            
        except Exception as e:
            print(f"❌ 检查过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    check_factor_dates() 