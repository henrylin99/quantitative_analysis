#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查数据库中的数据情况
"""

from app import create_app
from app.extensions import db

def check_data():
    app = create_app()
    with app.app_context():
        try:
            # 检查各表的数据情况
            tables = [
                'stock_daily_history',
                'stock_daily_basic', 
                'stock_moneyflow',
                'stock_cyq_perf',
                'stock_basic'
            ]
            
            for table in tables:
                try:
                    if table == 'stock_basic':
                        # stock_basic表没有trade_date字段
                        with db.engine.connect() as conn:
                            result = conn.execute(db.text(f'SELECT COUNT(*) as count FROM {table}'))
                            row = result.fetchone()
                            print(f'{table}: 记录数={row[0]}')
                    else:
                        with db.engine.connect() as conn:
                            result = conn.execute(db.text(f'SELECT COUNT(*) as count, MIN(trade_date) as min_date, MAX(trade_date) as max_date FROM {table}'))
                            row = result.fetchone()
                            print(f'{table}: 记录数={row[0]}, 最早日期={row[1]}, 最晚日期={row[2]}')
                except Exception as e:
                    print(f'{table}: 查询失败 - {e}')
            
            # 检查最近的交易日期
            print("\n=== 最近的交易日期 ===")
            with db.engine.connect() as conn:
                result = conn.execute(db.text('SELECT DISTINCT trade_date FROM stock_daily_history ORDER BY trade_date DESC LIMIT 10'))
                recent_dates = [row[0] for row in result.fetchall()]
                print(f'最近10个交易日: {recent_dates}')
            
            # 检查股票数量
            print("\n=== 股票数量 ===")
            with db.engine.connect() as conn:
                result = conn.execute(db.text('SELECT COUNT(DISTINCT ts_code) as stock_count FROM stock_daily_history'))
                row = result.fetchone()
                print(f'有行情数据的股票数量: {row[0]}')
            
        except Exception as e:
            print(f"检查数据失败: {e}")

if __name__ == '__main__':
    check_data() 