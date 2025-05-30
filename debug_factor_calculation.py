#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试因子计算过程
"""

from app import create_app
from app.extensions import db
from app.services.factor_engine import FactorEngine
import pandas as pd

def debug_factor_calculation():
    app = create_app()
    with app.app_context():
        try:
            # 创建因子引擎
            factor_engine = FactorEngine()
            
            # 测试数据获取
            print("=== 测试数据获取 ===")
            trade_date = "2025-05-23"
            
            # 获取少量股票进行测试
            with db.engine.connect() as conn:
                result = conn.execute(db.text('SELECT DISTINCT ts_code FROM stock_moneyflow LIMIT 5'))
                test_stocks = [row[0] for row in result.fetchall()]
                print(f"测试股票: {test_stocks}")
            
            # 测试获取资金流向数据
            data = factor_engine._get_factor_data('money_flow_strength', test_stocks, trade_date, trade_date)
            print(f"获取到的数据类型: {list(data.keys())}")
            
            if 'moneyflow' in data:
                moneyflow_df = data['moneyflow']
                print(f"资金流向数据形状: {moneyflow_df.shape}")
                print(f"资金流向数据列: {list(moneyflow_df.columns)}")
                print(f"资金流向数据前5行:")
                print(moneyflow_df.head())
                
                # 检查是否有空值
                print(f"空值情况:")
                print(moneyflow_df.isnull().sum())
                
                # 测试计算资金流向强度因子
                print("\n=== 测试资金流向强度因子计算 ===")
                result = factor_engine._money_flow_strength_factor(data, 'money_flow_strength')
                print(f"计算结果形状: {result.shape}")
                if not result.empty:
                    print("计算结果前5行:")
                    print(result.head())
                else:
                    print("计算结果为空")
            else:
                print("未获取到资金流向数据")
            
            # 测试筹码数据
            print("\n=== 测试筹码数据 ===")
            chip_data = factor_engine._get_factor_data('chip_concentration', test_stocks, trade_date, trade_date)
            if 'cyq' in chip_data:
                cyq_df = chip_data['cyq']
                print(f"筹码数据形状: {cyq_df.shape}")
                print(f"筹码数据列: {list(cyq_df.columns)}")
                print(f"筹码数据前5行:")
                print(cyq_df.head())
                
                # 测试计算筹码集中度因子
                print("\n=== 测试筹码集中度因子计算 ===")
                result = factor_engine._chip_concentration_factor(chip_data, 'chip_concentration')
                print(f"计算结果形状: {result.shape}")
                if not result.empty:
                    print("计算结果前5行:")
                    print(result.head())
                else:
                    print("计算结果为空")
            else:
                print("未获取到筹码数据")
                
        except Exception as e:
            print(f"调试失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    debug_factor_calculation() 