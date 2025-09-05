#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建一个简化的演示模型，使用模拟目标变量
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import FactorValues, MLModelDefinition
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import joblib
import os

def create_simple_demo_model():
    """创建简化的演示模型"""
    app = create_app()
    
    with app.app_context():
        print("🎯 创建简化的演示模型")
        print("=" * 60)
        
        try:
            # 1. 获取因子数据
            print("📊 获取因子数据...")
            factor_data = pd.read_sql('''
                SELECT ts_code, factor_id, factor_value
                FROM factor_values
                WHERE factor_id IN ('chip_concentration', 'money_flow_strength')
            ''', db.engine)
            
            print(f"   原始数据: {len(factor_data)} 条记录")
            
            # 2. 创建透视表
            print("🔄 创建特征矩阵...")
            feature_df = factor_data.pivot_table(
                index='ts_code',
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            ).reset_index()
            
            # 删除缺失值
            feature_df = feature_df.dropna()
            print(f"   特征矩阵: {len(feature_df)} 行 × {len(feature_df.columns)-1} 列")
            
            if len(feature_df) < 50:
                print("❌ 数据量太少，无法训练模型")
                return
            
            # 3. 创建模拟目标变量
            print("🎲 创建模拟目标变量...")
            np.random.seed(42)
            
            # 基于因子值创建合理的目标变量
            X = feature_df[['chip_concentration', 'money_flow_strength']].values
            
            # 标准化特征
            scaler = RobustScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 创建有意义的目标变量（模拟未来收益率）
            # 使用因子的线性组合加上噪声
            weights = np.array([0.3, 0.5])  # 因子权重
            signal = np.dot(X_scaled, weights)
            noise = np.random.normal(0, 0.02, len(signal))  # 2%的噪声
            y = signal * 0.05 + noise  # 缩放到合理的收益率范围
            
            print(f"   目标变量范围: {y.min():.4f} 至 {y.max():.4f}")
            print(f"   目标变量均值: {y.mean():.4f}, 标准差: {y.std():.4f}")
            
            # 4. 训练模型
            print("🚀 训练模型...")
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42
            )
            
            # 创建随机森林模型
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            
            # 训练
            model.fit(X_train, y_train)
            
            # 5. 评估模型
            print("📊 评估模型...")
            y_train_pred = model.predict(X_train)
            y_test_pred = model.predict(X_test)
            
            train_r2 = r2_score(y_train, y_train_pred)
            test_r2 = r2_score(y_test, y_test_pred)
            train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
            test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
            
            print(f"   训练R²: {train_r2:.4f}")
            print(f"   测试R²: {test_r2:.4f}")
            print(f"   训练RMSE: {train_rmse:.4f}")
            print(f"   测试RMSE: {test_rmse:.4f}")
            
            # 6. 保存模型
            print("💾 保存模型...")
            model_dir = 'models'
            os.makedirs(model_dir, exist_ok=True)
            
            model_path = os.path.join(model_dir, 'simple_demo_model.pkl')
            scaler_path = os.path.join(model_dir, 'simple_demo_scaler.pkl')
            
            joblib.dump(model, model_path)
            joblib.dump(scaler, scaler_path)
            
            print(f"   模型保存至: {model_path}")
            print(f"   缩放器保存至: {scaler_path}")
            
            # 7. 创建数据库模型定义
            print("📝 创建数据库模型定义...")
            
            # 检查是否已存在
            existing = MLModelDefinition.query.filter_by(model_id='simple_demo_model').first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
            
            # 创建新定义
            model_def = MLModelDefinition(
                model_id='simple_demo_model',
                model_name='简化演示模型',
                model_type='random_forest',
                factor_list=['chip_concentration', 'money_flow_strength'],
                target_type='simulated_return',
                model_params={
                    'n_estimators': 100,
                    'max_depth': 10,
                    'random_state': 42
                },
                training_config={
                    'test_size': 0.2,
                    'scaling_method': 'robust',
                    'use_simulated_target': True
                }
            )
            
            db.session.add(model_def)
            db.session.commit()
            
            print("✅ 简化演示模型创建完成！")
            print("\n📋 模型信息:")
            print(f"   模型ID: simple_demo_model")
            print(f"   特征数量: 2 (chip_concentration, money_flow_strength)")
            print(f"   样本数量: {len(feature_df)}")
            print(f"   训练样本: {len(X_train)}")
            print(f"   测试样本: {len(X_test)}")
            print(f"   模型性能: R² = {test_r2:.4f}")
            
            # 8. 演示预测
            print("\n🔮 演示预测...")
            sample_indices = np.random.choice(len(X_test), min(5, len(X_test)), replace=False)
            
            for i, idx in enumerate(sample_indices):
                pred = y_test_pred[idx]
                actual = y_test[idx]
                print(f"   样本{i+1}: 预测={pred:.4f}, 实际={actual:.4f}, 误差={abs(pred-actual):.4f}")
            
            print("\n🎉 现在您可以在Web界面中使用 'simple_demo_model' 进行预测了！")
            
        except Exception as e:
            print(f"❌ 创建过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    create_simple_demo_model() 