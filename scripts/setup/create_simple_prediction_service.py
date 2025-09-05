#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建简化的预测服务，用于演示模型的预测功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorValues, MLModelDefinition, MLPredictions
import pandas as pd
import numpy as np
import joblib
from datetime import datetime

def create_simple_prediction_service():
    """创建简化的预测服务"""
    app = create_app()
    
    with app.app_context():
        print("🔮 创建简化的预测服务")
        print("=" * 60)
        
        try:
            # 1. 加载模型
            print("📥 加载模型...")
            model_path = 'models/simple_demo_model.pkl'
            scaler_path = 'models/simple_demo_scaler.pkl'
            
            if not os.path.exists(model_path):
                print("❌ 模型文件不存在，请先运行 create_simple_demo_model.py")
                return
            
            model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
            print("   ✅ 模型加载成功")
            
            # 2. 获取最新的因子数据
            print("📊 获取最新因子数据...")
            factor_data = pd.read_sql('''
                SELECT ts_code, factor_id, factor_value
                FROM factor_values
                WHERE factor_id IN ('chip_concentration', 'money_flow_strength')
            ''', db.engine)
            
            # 创建特征矩阵
            feature_df = factor_data.pivot_table(
                index='ts_code',
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            ).reset_index()
            
            feature_df = feature_df.dropna()
            print(f"   可预测股票数量: {len(feature_df)}")
            
            # 3. 进行预测
            print("🚀 进行预测...")
            X = feature_df[['chip_concentration', 'money_flow_strength']].values
            X_scaled = scaler.transform(X)
            predictions = model.predict(X_scaled)
            
            # 4. 创建预测结果
            print("📝 保存预测结果...")
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # 清除旧的预测结果
            MLPredictions.query.filter_by(
                model_id='simple_demo_model',
                trade_date=current_date
            ).delete()
            
            # 保存新的预测结果
            prediction_results = []
            for i, ts_code in enumerate(feature_df['ts_code']):
                pred_result = MLPredictions(
                    model_id='simple_demo_model',
                    ts_code=ts_code,
                    trade_date=current_date,
                    predicted_return=float(predictions[i]),
                    probability_score=float((predictions[i] - predictions.min()) / (predictions.max() - predictions.min())),
                    rank_score=int(len(predictions) - np.argsort(np.argsort(predictions))[i])
                )
                prediction_results.append(pred_result)
            
            db.session.add_all(prediction_results)
            db.session.commit()
            
            print(f"   ✅ 保存了 {len(prediction_results)} 条预测结果")
            
            # 5. 显示预测统计
            print("\n📊 预测统计:")
            print(f"   预测收益率范围: {predictions.min():.4f} 至 {predictions.max():.4f}")
            print(f"   预测收益率均值: {predictions.mean():.4f}")
            print(f"   预测收益率标准差: {predictions.std():.4f}")
            
            # 6. 显示前10名股票
            print("\n🏆 预测收益率前10名股票:")
            top_indices = np.argsort(predictions)[-10:][::-1]
            
            for i, idx in enumerate(top_indices):
                ts_code = feature_df.iloc[idx]['ts_code']
                pred_return = predictions[idx]
                chip_conc = feature_df.iloc[idx]['chip_concentration']
                money_flow = feature_df.iloc[idx]['money_flow_strength']
                
                print(f"   {i+1:2d}. {ts_code}: {pred_return:+.4f} (筹码集中度: {chip_conc:.4f}, 资金流强度: {money_flow:.4f})")
            
            print("\n✅ 简化预测服务创建完成！")
            print("🎯 现在您可以在Web界面的'模型管理'页面中:")
            print("   1. 查看 'simple_demo_model' 模型")
            print("   2. 点击'预测'按钮进行预测")
            print("   3. 查看预测结果和排名")
            
        except Exception as e:
            print(f"❌ 创建过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    create_simple_prediction_service() 