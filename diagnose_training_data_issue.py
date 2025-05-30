#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断训练数据为空的问题
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorValues, MLModelDefinition, StockDailyHistory
from sqlalchemy import text
import pandas as pd

def diagnose_training_data_issue():
    """诊断训练数据为空的问题"""
    app = create_app()
    
    with app.app_context():
        print("🔍 诊断训练数据为空的问题")
        print("=" * 60)
        
        try:
            # 1. 检查working_demo_model的配置
            model = MLModelDefinition.query.filter_by(model_id='working_demo_model').first()
            if not model:
                print("❌ 未找到working_demo_model")
                return
            
            print(f"📋 模型配置:")
            print(f"   模型ID: {model.model_id}")
            print(f"   因子列表: {model.factor_list}")
            print(f"   目标类型: {model.target_type}")
            
            # 2. 检查因子数据
            print(f"\n📊 检查因子数据:")
            for factor_id in model.factor_list:
                count = FactorValues.query.filter_by(factor_id=factor_id).count()
                print(f"   {factor_id}: {count} 条记录")
                
                if count > 0:
                    sample = FactorValues.query.filter_by(factor_id=factor_id).first()
                    print(f"      样本: {sample.ts_code}, {sample.trade_date}, {sample.factor_value}")
            
            # 3. 获取因子数据并创建透视表
            print(f"\n🔄 创建因子透视表:")
            factor_query = FactorValues.query.filter(
                FactorValues.factor_id.in_(model.factor_list)
            )
            
            factor_data = pd.read_sql(factor_query.statement, db.engine)
            print(f"   原始因子数据: {len(factor_data)} 条")
            
            if factor_data.empty:
                print("   ❌ 因子数据为空")
                return
            
            # 透视表
            feature_df = factor_data.pivot_table(
                index=['ts_code', 'trade_date'],
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            ).reset_index()
            
            print(f"   透视表: {len(feature_df)} 行")
            print(f"   日期范围: {feature_df['trade_date'].min()} 至 {feature_df['trade_date'].max()}")
            print(f"   股票数量: {feature_df['ts_code'].nunique()}")
            
            # 4. 检查价格数据
            print(f"\n📈 检查价格数据:")
            ts_codes = feature_df['ts_code'].unique()
            print(f"   需要价格数据的股票: {len(ts_codes)} 只")
            
            # 检查有多少股票有价格数据
            price_count_query = text('''
                SELECT COUNT(DISTINCT ts_code) as stock_count,
                       MIN(trade_date) as min_date,
                       MAX(trade_date) as max_date,
                       COUNT(*) as total_records
                FROM stock_daily_history
                WHERE ts_code IN :ts_codes
            ''')
            
            result = db.session.execute(price_count_query, {'ts_codes': tuple(ts_codes[:100])})  # 限制查询数量
            price_info = result.fetchone()
            
            print(f"   有价格数据的股票: {price_info.stock_count} 只")
            print(f"   价格数据日期范围: {price_info.min_date} 至 {price_info.max_date}")
            print(f"   价格数据总记录: {price_info.total_records} 条")
            
            # 5. 检查目标变量计算
            print(f"\n🎯 检查目标变量计算:")
            target_type = model.target_type
            period = int(target_type.split('_')[1].replace('d', ''))
            print(f"   目标类型: {target_type}")
            print(f"   预测周期: {period} 天")
            
            # 检查是否有足够的未来数据
            feature_date = feature_df['trade_date'].max()
            print(f"   因子数据最新日期: {feature_date}")
            
            # 查询价格数据中是否有未来日期
            future_price_query = text('''
                SELECT COUNT(*) as count,
                       MAX(trade_date) as max_date
                FROM stock_daily_history
                WHERE trade_date > :feature_date
                AND ts_code IN :ts_codes
            ''')
            
            result = db.session.execute(future_price_query, {
                'feature_date': feature_date,
                'ts_codes': tuple(ts_codes[:10])  # 检查前10只股票
            })
            future_info = result.fetchone()
            
            print(f"   未来价格数据: {future_info.count} 条")
            print(f"   价格数据最新日期: {future_info.max_date}")
            
            # 6. 分析问题
            print(f"\n💡 问题分析:")
            
            if price_info.stock_count == 0:
                print("   ❌ 主要问题: 完全没有价格数据")
                print("   🔧 解决方案: 需要导入股票价格数据到stock_daily_history表")
            elif future_info.count == 0:
                print("   ❌ 主要问题: 没有未来价格数据来计算目标变量")
                print(f"   📅 因子数据日期: {feature_date}")
                print(f"   📅 需要的未来日期: {feature_date} + {period}天")
                print("   🔧 解决方案:")
                print("      1. 导入更多历史价格数据（推荐）")
                print("      2. 或者使用简化演示模型（simple_demo_model）")
                print("      3. 或者修改目标类型为模拟数据")
            else:
                print("   ⚠️  数据存在但可能不匹配")
                print("   🔧 建议检查数据质量和完整性")
            
            # 7. 提供具体的解决建议
            print(f"\n🚀 推荐解决方案:")
            print("1. 【最简单】使用已经可用的simple_demo_model")
            print("2. 【推荐】将working_demo_model改为使用模拟目标变量")
            print("3. 【完整】导入历史股票价格数据")
            
        except Exception as e:
            print(f"❌ 诊断过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    diagnose_training_data_issue() 