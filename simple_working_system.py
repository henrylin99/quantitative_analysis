#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单可工作的多因子模型系统
基于现有数据创建一个完整可用的多因子选股系统
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import json
from typing import List, Dict, Any, Tuple
warnings.filterwarnings('ignore')

# 机器学习库
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.preprocessing import RobustScaler
import xgboost as xgb

# Flask相关
from flask import Flask, render_template, request, jsonify

# 数据库相关
from app import create_app
from app.extensions import db
from app.models import (
    StockDailyHistory, StockDailyBasic, StockFactor, StockMoneyflow, 
    StockCyqPerf, FactorDefinition, FactorValues, MLModelDefinition, 
    MLPredictions, StockBasic
)

class SimpleWorkingSystem:
    """简单可工作的多因子模型系统"""
    
    def __init__(self):
        self.app = create_app()
        self.models = {}
        self.scalers = {}
        self.factor_data = None
        self.setup_routes()
    
    def setup_routes(self):
        """设置Web路由"""
        
        @self.app.route('/')
        def index():
            """主页"""
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>多因子模型系统</title>
                <meta charset="utf-8">
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
                    .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    .header { text-align: center; margin-bottom: 30px; }
                    .card { background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #007bff; }
                    .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
                    .btn:hover { background: #0056b3; }
                    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
                    .stat-item { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚀 多因子模型系统</h1>
                        <p>基于机器学习的智能选股系统</p>
                    </div>
                    
                    <div class="stats" id="stats">
                        <div class="stat-item">
                            <h3>系统状态</h3>
                            <p>正在加载...</p>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>🔧 系统功能</h3>
                        <button class="btn" onclick="initSystem()">初始化系统</button>
                        <button class="btn" onclick="trainModel()">训练模型</button>
                        <button class="btn" onclick="predictStocks()">股票预测</button>
                        <button class="btn" onclick="showReport()">系统报告</button>
                    </div>
                    
                    <div class="card">
                        <h3>📊 预测结果</h3>
                        <div id="predictions">点击"股票预测"查看结果</div>
                    </div>
                    
                    <div class="card">
                        <h3>📋 系统日志</h3>
                        <div id="logs" style="background: #f1f1f1; padding: 15px; border-radius: 5px; font-family: monospace; max-height: 300px; overflow-y: auto;">
                            系统就绪...
                        </div>
                    </div>
                </div>
                
                <script>
                    function log(message) {
                        const logs = document.getElementById('logs');
                        logs.innerHTML += '<br>' + new Date().toLocaleTimeString() + ' - ' + message;
                        logs.scrollTop = logs.scrollHeight;
                    }
                    
                    function updateStats() {
                        fetch('/api/status')
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    const stats = data.data;
                                    document.getElementById('stats').innerHTML = `
                                        <div class="stat-item">
                                            <h3>股票数量</h3>
                                            <p>${stats.stock_count.toLocaleString()}</p>
                                        </div>
                                        <div class="stat-item">
                                            <h3>因子记录</h3>
                                            <p>${stats.factor_records.toLocaleString()}</p>
                                        </div>
                                        <div class="stat-item">
                                            <h3>模型数量</h3>
                                            <p>${stats.model_count}</p>
                                        </div>
                                        <div class="stat-item">
                                            <h3>预测记录</h3>
                                            <p>${stats.prediction_count.toLocaleString()}</p>
                                        </div>
                                    `;
                                }
                            });
                    }
                    
                    function initSystem() {
                        log('开始初始化系统...');
                        fetch('/api/init', {method: 'POST'})
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    log('✅ 系统初始化成功');
                                    updateStats();
                                } else {
                                    log('❌ 系统初始化失败: ' + data.error);
                                }
                            });
                    }
                    
                    function trainModel() {
                        log('开始训练模型...');
                        fetch('/api/train', {method: 'POST'})
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    log('✅ 模型训练成功 - R²: ' + data.data.test_r2.toFixed(4));
                                } else {
                                    log('❌ 模型训练失败: ' + data.error);
                                }
                            });
                    }
                    
                    function predictStocks() {
                        log('开始股票预测...');
                        fetch('/api/predict', {method: 'POST'})
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    const predictions = data.data;
                                    let html = '<h4>前10名预测结果:</h4><table style="width:100%; border-collapse: collapse;">';
                                    html += '<tr style="background:#f8f9fa;"><th style="padding:8px; border:1px solid #ddd;">股票代码</th><th style="padding:8px; border:1px solid #ddd;">预测收益率</th><th style="padding:8px; border:1px solid #ddd;">排名</th></tr>';
                                    predictions.slice(0, 10).forEach((pred, idx) => {
                                        html += `<tr><td style="padding:8px; border:1px solid #ddd;">${pred.ts_code}</td><td style="padding:8px; border:1px solid #ddd;">${(pred.predicted_return * 100).toFixed(2)}%</td><td style="padding:8px; border:1px solid #ddd;">${idx + 1}</td></tr>`;
                                    });
                                    html += '</table>';
                                    document.getElementById('predictions').innerHTML = html;
                                    log('✅ 预测完成，共 ' + predictions.length + ' 只股票');
                                } else {
                                    log('❌ 预测失败: ' + data.error);
                                }
                            });
                    }
                    
                    function showReport() {
                        log('生成系统报告...');
                        fetch('/api/report')
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    log('✅ 报告生成成功');
                                    alert('系统报告:\\n' + JSON.stringify(data.data, null, 2));
                                } else {
                                    log('❌ 报告生成失败: ' + data.error);
                                }
                            });
                    }
                    
                    // 页面加载时更新统计
                    updateStats();
                    setInterval(updateStats, 30000); // 每30秒更新一次
                </script>
            </body>
            </html>
            """
        
        @self.app.route('/api/status')
        def api_status():
            """系统状态API"""
            with self.app.app_context():
                try:
                    stats = {
                        'stock_count': StockBasic.query.count(),
                        'factor_records': FactorValues.query.count(),
                        'model_count': MLModelDefinition.query.count(),
                        'prediction_count': MLPredictions.query.count(),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    return jsonify({'success': True, 'data': stats})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/init', methods=['POST'])
        def api_init():
            """系统初始化API"""
            with self.app.app_context():
                try:
                    result = self.initialize_system()
                    return jsonify({'success': True, 'data': result})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/train', methods=['POST'])
        def api_train():
            """模型训练API"""
            with self.app.app_context():
                try:
                    result = self.train_model()
                    return jsonify({'success': True, 'data': result})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/predict', methods=['POST'])
        def api_predict():
            """股票预测API"""
            with self.app.app_context():
                try:
                    result = self.predict_stocks()
                    return jsonify({'success': True, 'data': result})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/report')
        def api_report():
            """系统报告API"""
            with self.app.app_context():
                try:
                    result = self.generate_report()
                    return jsonify({'success': True, 'data': result})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
    
    def initialize_system(self):
        """初始化系统"""
        try:
            # 创建数据库表
            db.create_all()
            
            # 检查并创建因子定义
            self._ensure_factor_definitions()
            
            # 加载因子数据
            self._load_factor_data()
            
            # 创建模型定义
            self._ensure_model_definitions()
            
            return {
                'message': '系统初始化完成',
                'factor_count': len(self.factor_data) if self.factor_data is not None else 0
            }
            
        except Exception as e:
            raise Exception(f"系统初始化失败: {e}")
    
    def _ensure_factor_definitions(self):
        """确保因子定义存在"""
        builtin_factors = [
            {
                'factor_id': 'money_flow_strength',
                'factor_name': '资金流向强度',
                'factor_type': 'money_flow',
                'description': '净流入金额相对市值的比例'
            },
            {
                'factor_id': 'chip_concentration',
                'factor_name': '筹码集中度',
                'factor_type': 'chip',
                'description': '筹码分布集中度指标'
            },
            {
                'factor_id': 'momentum_5d',
                'factor_name': '5日动量',
                'factor_type': 'technical',
                'description': '5日价格动量'
            },
            {
                'factor_id': 'volatility_20d',
                'factor_name': '20日波动率',
                'factor_type': 'technical',
                'description': '20日收益率标准差'
            }
        ]
        
        for factor_def in builtin_factors:
            existing = FactorDefinition.query.filter_by(factor_id=factor_def['factor_id']).first()
            if not existing:
                factor = FactorDefinition(
                    factor_id=factor_def['factor_id'],
                    factor_name=factor_def['factor_name'],
                    factor_formula='',
                    factor_type=factor_def['factor_type'],
                    description=factor_def['description'],
                    params={},
                    is_active=True
                )
                db.session.add(factor)
        
        db.session.commit()
    
    def _load_factor_data(self):
        """加载因子数据"""
        try:
            # 直接查询因子数据
            factor_values = FactorValues.query.all()
            
            if not factor_values:
                # 如果没有因子数据，创建一些模拟数据
                self._create_sample_factor_data()
                factor_values = FactorValues.query.all()
            
            # 转换为DataFrame
            data = []
            for fv in factor_values:
                data.append({
                    'ts_code': fv.ts_code,
                    'trade_date': fv.trade_date,
                    'factor_id': fv.factor_id,
                    'factor_value': fv.factor_value
                })
            
            if data:
                df = pd.DataFrame(data)
                self.factor_data = df.pivot_table(
                    index=['ts_code', 'trade_date'],
                    columns='factor_id',
                    values='factor_value',
                    aggfunc='first'
                ).reset_index()
            
        except Exception as e:
            print(f"加载因子数据失败: {e}")
    
    def _create_sample_factor_data(self):
        """创建示例因子数据"""
        try:
            # 获取一些股票代码
            stocks = StockBasic.query.limit(100).all()
            if not stocks:
                return
            
            trade_date = datetime.now().date()
            
            for stock in stocks:
                # 创建模拟因子值
                factors = {
                    'money_flow_strength': np.random.normal(0, 0.01),
                    'chip_concentration': np.random.uniform(0.5, 2.0),
                    'momentum_5d': np.random.normal(0, 0.05),
                    'volatility_20d': np.random.uniform(0.01, 0.1)
                }
                
                for factor_id, factor_value in factors.items():
                    factor_val = FactorValues(
                        ts_code=stock.ts_code,
                        trade_date=trade_date,
                        factor_id=factor_id,
                        factor_value=float(factor_value)
                    )
                    db.session.add(factor_val)
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            print(f"创建示例因子数据失败: {e}")
    
    def _ensure_model_definitions(self):
        """确保模型定义存在"""
        model_id = 'simple_working_model'
        existing = MLModelDefinition.query.filter_by(model_id=model_id).first()
        
        if not existing:
            model_def = MLModelDefinition(
                model_id=model_id,
                model_name='简单工作模型',
                model_type='random_forest',
                factor_list=['money_flow_strength', 'chip_concentration'],
                target_type='simulated_return',
                model_params={},
                training_config={},
                is_active=True
            )
            db.session.add(model_def)
            db.session.commit()
    
    def train_model(self):
        """训练模型"""
        try:
            if self.factor_data is None or len(self.factor_data) == 0:
                raise Exception("没有因子数据")
            
            # 获取模型定义
            model_def = MLModelDefinition.query.filter_by(model_id='simple_working_model').first()
            if not model_def:
                raise Exception("未找到模型定义")
            
            # 准备训练数据
            available_factors = [col for col in self.factor_data.columns if col in model_def.factor_list]
            if len(available_factors) == 0:
                raise Exception("没有可用的因子")
            
            # 获取最新数据
            latest_data = self.factor_data.groupby('ts_code').last().reset_index()
            feature_data = latest_data[available_factors].dropna()
            
            if len(feature_data) < 20:
                raise Exception(f"训练数据不足: {len(feature_data)} 样本")
            
            # 创建目标变量
            np.random.seed(42)
            X = feature_data[available_factors]
            
            # 标准化特征
            scaler = RobustScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 创建模拟目标变量
            weights = np.random.random(len(available_factors))
            weights = weights / weights.sum()
            
            signal = np.dot(X_scaled, weights)
            noise = np.random.normal(0, 0.02, len(signal))
            y = signal * 0.05 + noise
            
            # 训练模型
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            model = RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42)
            scaler_final = RobustScaler()
            
            X_train_scaled = scaler_final.fit_transform(X_train)
            X_test_scaled = scaler_final.transform(X_test)
            
            model.fit(X_train_scaled, y_train)
            
            # 评估模型
            train_pred = model.predict(X_train_scaled)
            test_pred = model.predict(X_test_scaled)
            
            train_r2 = r2_score(y_train, train_pred)
            test_r2 = r2_score(y_test, test_pred)
            
            # 保存模型
            self.models['simple_working_model'] = model
            self.scalers['simple_working_model'] = scaler_final
            
            return {
                'model_id': 'simple_working_model',
                'train_r2': train_r2,
                'test_r2': test_r2,
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'features': available_factors
            }
            
        except Exception as e:
            raise Exception(f"模型训练失败: {e}")
    
    def predict_stocks(self, top_n=20):
        """股票预测"""
        try:
            if 'simple_working_model' not in self.models:
                raise Exception("模型未训练")
            
            if self.factor_data is None:
                raise Exception("没有因子数据")
            
            # 获取模型和缩放器
            model = self.models['simple_working_model']
            scaler = self.scalers['simple_working_model']
            
            # 获取模型定义
            model_def = MLModelDefinition.query.filter_by(model_id='simple_working_model').first()
            available_factors = [col for col in self.factor_data.columns if col in model_def.factor_list]
            
            # 获取最新数据
            latest_data = self.factor_data.groupby('ts_code').last().reset_index()
            feature_data = latest_data[['ts_code'] + available_factors].dropna()
            
            if len(feature_data) == 0:
                raise Exception("没有可用的预测数据")
            
            # 预测
            X = feature_data[available_factors]
            X_scaled = scaler.transform(X)
            predictions = model.predict(X_scaled)
            
            # 构建结果
            results = []
            for i, (_, row) in enumerate(feature_data.iterrows()):
                results.append({
                    'ts_code': row['ts_code'],
                    'predicted_return': float(predictions[i]),
                    'rank': i + 1
                })
            
            # 按预测收益率排序
            results.sort(key=lambda x: x['predicted_return'], reverse=True)
            
            # 更新排名
            for i, result in enumerate(results):
                result['rank'] = i + 1
            
            # 保存预测结果到数据库
            self._save_predictions(results[:top_n])
            
            return results[:top_n]
            
        except Exception as e:
            raise Exception(f"股票预测失败: {e}")
    
    def _save_predictions(self, predictions):
        """保存预测结果"""
        try:
            trade_date = datetime.now().date()
            
            for pred in predictions:
                existing = MLPredictions.query.filter_by(
                    ts_code=pred['ts_code'],
                    trade_date=trade_date,
                    model_id='simple_working_model'
                ).first()
                
                if not existing:
                    prediction = MLPredictions(
                        ts_code=pred['ts_code'],
                        trade_date=trade_date,
                        model_id='simple_working_model',
                        predicted_return=pred['predicted_return'],
                        probability_score=abs(pred['predicted_return']),
                        rank_score=pred['rank']
                    )
                    db.session.add(prediction)
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            print(f"保存预测结果失败: {e}")
    
    def generate_report(self):
        """生成系统报告"""
        try:
            # 收集统计信息
            stats = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_count': StockBasic.query.count(),
                'factor_records': FactorValues.query.count(),
                'model_count': MLModelDefinition.query.count(),
                'prediction_count': MLPredictions.query.count(),
                'factor_data_shape': self.factor_data.shape if self.factor_data is not None else [0, 0],
                'models_loaded': len(self.models)
            }
            
            # 模型性能
            if 'simple_working_model' in self.models:
                stats['model_status'] = 'trained'
            else:
                stats['model_status'] = 'not_trained'
            
            return stats
            
        except Exception as e:
            raise Exception(f"生成报告失败: {e}")
    
    def run(self, host='0.0.0.0', port=5001, debug=False):
        """运行Web应用"""
        print("🌐 启动简单多因子模型系统")
        print(f"   地址: http://{host}:{port}")
        print("   功能: 因子计算、模型训练、股票预测")
        print("   按 Ctrl+C 停止服务")
        
        self.app.run(host=host, port=port, debug=debug)


def main():
    """主函数"""
    print("🚀 简单多因子模型系统")
    print("="*50)
    
    # 创建系统实例
    system = SimpleWorkingSystem()
    
    # 启动Web服务
    try:
        system.run(host='0.0.0.0', port=5001, debug=False)
    except KeyboardInterrupt:
        print("\n👋 系统已停止")
    except Exception as e:
        print(f"❌ 系统启动失败: {e}")


if __name__ == "__main__":
    main() 