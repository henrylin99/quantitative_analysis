#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试机器学习训练过程
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorDefinition, FactorValues, MLModelDefinition, StockDailyHistory
from sqlalchemy import text
import pandas as pd
from datetime import datetime, timedelta

def debug_ml_training():
    """调试机器学习训练过程"""
    app = create_app()
    
    with app.app_context():
        print("🔍 调试机器学习训练过程")
        print("=" * 60)
        
        try:
            # 1. 检查模型定义
            print("1️⃣ 检查模型定义...")
            models = MLModelDefinition.query.all()
            print(f"   找到 {len(models)} 个模型定义")
            
            if not models:
                print("   ❌ 没有模型定义，无法训练")
                return
            
            # 使用第一个模型进行调试
            model = models[0]
            print(f"   🎯 使用模型: {model.model_id} - {model.model_name}")
            print(f"   📋 需要的因子: {model.factor_list}")
            
            # 2. 检查因子数据
            print("\n2️⃣ 检查因子数据...")
            for factor_id in model.factor_list:
                count = FactorValues.query.filter_by(factor_id=factor_id).count()
                print(f"   📊 {factor_id}: {count} 条记录")
                
                if count > 0:
                    # 查看数据样本
                    sample = FactorValues.query.filter_by(factor_id=factor_id).first()
                    print(f"      样本: {sample.ts_code}, {sample.trade_date}, {sample.factor_value}")
            
            # 3. 模拟数据准备过程
            print("\n3️⃣ 模拟数据准备过程...")
            start_date = '2023-01-01'
            end_date = '2023-12-31'
            
            # 获取因子数据
            factor_query = FactorValues.query.filter(
                FactorValues.factor_id.in_(model.factor_list),
                FactorValues.trade_date >= start_date,
                FactorValues.trade_date <= end_date
            ).order_by(FactorValues.ts_code, FactorValues.trade_date, FactorValues.factor_id)
            
            factor_data = pd.read_sql(factor_query.statement, db.engine)
            print(f"   📈 原始因子数据: {len(factor_data)} 条记录")
            
            if factor_data.empty:
                print("   ❌ 因子数据为空")
                return
            
            print(f"   📅 日期范围: {factor_data['trade_date'].min()} 至 {factor_data['trade_date'].max()}")
            print(f"   🏢 股票数量: {factor_data['ts_code'].nunique()}")
            print(f"   📊 因子类型: {factor_data['factor_id'].unique()}")
            
            # 透视表
            print("\n4️⃣ 创建透视表...")
            try:
                feature_df = factor_data.pivot_table(
                    index=['ts_code', 'trade_date'],
                    columns='factor_id',
                    values='factor_value',
                    aggfunc='first'
                ).reset_index()
                
                print(f"   ✅ 透视表创建成功: {len(feature_df)} 行")
                print(f"   📊 特征列: {feature_df.columns.tolist()}")
                
                # 检查缺失值
                missing_info = feature_df.isnull().sum()
                print(f"   🔍 缺失值情况:")
                for col, missing_count in missing_info.items():
                    if missing_count > 0:
                        print(f"      {col}: {missing_count} 个缺失值")
                
            except Exception as e:
                print(f"   ❌ 透视表创建失败: {e}")
                return
            
            # 5. 检查价格数据
            print("\n5️⃣ 检查价格数据...")
            ts_codes = feature_df['ts_code'].unique()[:5]  # 只检查前5只股票
            print(f"   🔍 检查前5只股票的价格数据: {ts_codes}")
            
            for ts_code in ts_codes:
                price_count = StockDailyHistory.query.filter_by(ts_code=ts_code).count()
                print(f"   📈 {ts_code}: {price_count} 条价格记录")
                
                if price_count > 0:
                    # 查看最新价格
                    latest_price = StockDailyHistory.query.filter_by(ts_code=ts_code).order_by(StockDailyHistory.trade_date.desc()).first()
                    print(f"      最新: {latest_price.trade_date}, 收盘价: {latest_price.close}")
            
            # 6. 模拟目标变量计算
            print("\n6️⃣ 模拟目标变量计算...")
            target_type = model.target_type
            period = int(target_type.split('_')[1].replace('d', ''))
            print(f"   🎯 目标类型: {target_type}, 周期: {period} 天")
            
            # 获取一只股票的价格数据进行测试
            test_ts_code = ts_codes[0]
            price_query = StockDailyHistory.query.filter(
                StockDailyHistory.ts_code == test_ts_code,
                StockDailyHistory.trade_date >= start_date,
                StockDailyHistory.trade_date <= end_date
            ).order_by(StockDailyHistory.trade_date)
            
            price_data = pd.read_sql(price_query.statement, db.engine)
            print(f"   📊 测试股票 {test_ts_code} 价格数据: {len(price_data)} 条")
            
            if len(price_data) > period:
                # 计算收益率
                price_data['future_return'] = price_data['close'].pct_change(period).shift(-period)
                valid_returns = price_data['future_return'].dropna()
                print(f"   📈 有效收益率数据: {len(valid_returns)} 条")
                print(f"   📊 收益率范围: {valid_returns.min():.4f} 至 {valid_returns.max():.4f}")
            
            print("\n✅ 调试完成！")
            
            # 7. 给出建议
            print("\n💡 建议:")
            if len(factor_data) == 0:
                print("   1. 需要计算因子数据")
            elif len(feature_df) == 0:
                print("   2. 因子数据透视失败，检查数据格式")
            else:
                print("   3. 数据看起来正常，可能是其他问题")
                print("   4. 建议检查目标变量计算逻辑")
                print("   5. 或者使用演示模型进行测试")
            
        except Exception as e:
            print(f"❌ 调试过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_ml_training() 