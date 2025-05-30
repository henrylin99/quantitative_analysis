#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查因子值表的数据
"""

from app import create_app
from app.extensions import db

def check_factor_values():
    app = create_app()
    with app.app_context():
        try:
            # 检查因子值表的数据情况
            print("=== 因子值表数据检查 ===")
            
            with db.engine.connect() as conn:
                # 总记录数
                result = conn.execute(db.text('SELECT COUNT(*) as count FROM factor_values'))
                total_count = result.fetchone()[0]
                print(f"因子值表总记录数: {total_count}")
                
                # 按因子ID统计
                result = conn.execute(db.text('SELECT factor_id, COUNT(*) as count FROM factor_values GROUP BY factor_id ORDER BY count DESC'))
                print("\n按因子ID统计:")
                for row in result.fetchall():
                    print(f"  {row[0]}: {row[1]} 条记录")
                
                # 按交易日期统计
                result = conn.execute(db.text('SELECT trade_date, COUNT(*) as count FROM factor_values GROUP BY trade_date ORDER BY trade_date DESC'))
                print("\n按交易日期统计:")
                for row in result.fetchall():
                    print(f"  {row[0]}: {row[1]} 条记录")
                
                # 查看最新的几条记录
                result = conn.execute(db.text('SELECT ts_code, trade_date, factor_id, factor_value, percentile_rank, z_score FROM factor_values ORDER BY created_at DESC LIMIT 10'))
                print("\n最新的10条记录 (ts_code | trade_date | factor_id | factor_value | percentile_rank | z_score):")
                for row in result.fetchall():
                    print(f"  {row[0]} | {row[1]} | {row[2]} | {row[3]:.6f} | {row[4]:.2f} | {row[5]:.6f}")
                
                # 检查特定因子的数据
                print("\n=== 检查特定因子数据 ===")
                for factor_id in ['money_flow_strength', 'chip_concentration']:
                    result = conn.execute(db.text(f"SELECT COUNT(*) as count, MIN(factor_value) as min_val, MAX(factor_value) as max_val, AVG(factor_value) as avg_val FROM factor_values WHERE factor_id = '{factor_id}'"))
                    row = result.fetchone()
                    if row[0] > 0:
                        print(f"{factor_id}: {row[0]}条记录, 最小值={row[1]:.6f}, 最大值={row[2]:.6f}, 平均值={row[3]:.6f}")
                    else:
                        print(f"{factor_id}: 无数据")
                
        except Exception as e:
            print(f"检查失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    check_factor_values() 