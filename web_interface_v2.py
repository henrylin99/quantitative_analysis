#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子模型系统Web界面 V2.0
提供现代化的Web界面用于系统管理和监控
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
from typing import List, Dict, Any

from app import create_app
from app.extensions import db
from app.models import (
    FactorDefinition, FactorValues, MLModelDefinition, MLPredictions,
    StockBasic, StockDailyHistory
)

class MultifactorWebInterface:
    """多因子模型Web界面"""
    
    def __init__(self):
        self.app = create_app()
        self.setup_routes()
    
    def setup_routes(self):
        """设置路由"""
        
        @self.app.route('/')
        def index():
            """主页"""
            return render_template('multifactor_dashboard.html')
        
        @self.app.route('/dashboard')
        def dashboard():
            """仪表板"""
            with self.app.app_context():
                try:
                    # 获取系统统计
                    stats = self.get_system_stats()
                    return render_template('dashboard.html', stats=stats)
                except Exception as e:
                    return render_template('error.html', error=str(e))
        
        @self.app.route('/factors')
        def factors():
            """因子管理页面"""
            with self.app.app_context():
                try:
                    factors = FactorDefinition.query.all()
                    factor_stats = self.get_factor_stats()
                    return render_template('factors.html', factors=factors, stats=factor_stats)
                except Exception as e:
                    return render_template('error.html', error=str(e))
        
        @self.app.route('/models')
        def models():
            """模型管理页面"""
            with self.app.app_context():
                try:
                    models = MLModelDefinition.query.all()
                    model_stats = self.get_model_stats()
                    return render_template('models.html', models=models, stats=model_stats)
                except Exception as e:
                    return render_template('error.html', error=str(e))
        
        @self.app.route('/predictions')
        def predictions():
            """预测结果页面"""
            with self.app.app_context():
                try:
                    recent_predictions = self.get_recent_predictions()
                    return render_template('predictions.html', predictions=recent_predictions)
                except Exception as e:
                    return render_template('error.html', error=str(e))
        
        # API路由
        @self.app.route('/api/system/status')
        def api_system_status():
            """系统状态API"""
            with self.app.app_context():
                try:
                    status = self.get_system_stats()
                    return jsonify({'success': True, 'data': status})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/factors/list')
        def api_factors_list():
            """因子列表API"""
            with self.app.app_context():
                try:
                    factors = FactorDefinition.query.all()
                    factor_data = [factor.to_dict() for factor in factors]
                    return jsonify({'success': True, 'data': factor_data})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/factors/calculate', methods=['POST'])
        def api_calculate_factors():
            """计算因子API"""
            with self.app.app_context():
                try:
                    data = request.get_json()
                    factor_ids = data.get('factor_ids', [])
                    trade_date = data.get('trade_date', datetime.now().strftime('%Y-%m-%d'))
                    
                    result = self.calculate_factors(factor_ids, trade_date)
                    return jsonify({'success': True, 'data': result})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/models/list')
        def api_models_list():
            """模型列表API"""
            with self.app.app_context():
                try:
                    models = MLModelDefinition.query.all()
                    model_data = [model.to_dict() for model in models]
                    return jsonify({'success': True, 'data': model_data})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/models/predict/<model_id>', methods=['POST'])
        def api_model_predict(model_id):
            """模型预测API"""
            with self.app.app_context():
                try:
                    data = request.get_json() or {}
                    trade_date = data.get('trade_date', datetime.now().strftime('%Y-%m-%d'))
                    top_n = data.get('top_n', 20)
                    
                    predictions = self.predict_with_model(model_id, trade_date, top_n)
                    return jsonify({'success': True, 'data': predictions})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/predictions/recent')
        def api_recent_predictions():
            """最近预测结果API"""
            with self.app.app_context():
                try:
                    predictions = self.get_recent_predictions()
                    return jsonify({'success': True, 'data': predictions})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})
    
    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        try:
            stats = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_stats': {
                    'stock_count': StockBasic.query.count(),
                    'history_records': StockDailyHistory.query.count(),
                    'factor_records': FactorValues.query.count(),
                    'factor_definitions': FactorDefinition.query.count(),
                    'model_definitions': MLModelDefinition.query.count(),
                    'prediction_records': MLPredictions.query.count()
                },
                'recent_activity': {
                    'latest_factor_date': self.get_latest_factor_date(),
                    'latest_prediction_date': self.get_latest_prediction_date(),
                    'active_models': MLModelDefinition.query.filter_by(is_active=True).count()
                }
            }
            return stats
        except Exception as e:
            return {'error': str(e)}
    
    def get_factor_stats(self) -> List[Dict[str, Any]]:
        """获取因子统计信息"""
        try:
            result = db.session.execute("""
                SELECT 
                    fd.factor_id,
                    fd.factor_name,
                    fd.factor_type,
                    COUNT(fv.factor_value) as record_count,
                    MIN(fv.trade_date) as min_date,
                    MAX(fv.trade_date) as max_date,
                    AVG(fv.factor_value) as avg_value,
                    STDDEV(fv.factor_value) as std_value
                FROM factor_definition fd
                LEFT JOIN factor_values fv ON fd.factor_id = fv.factor_id
                GROUP BY fd.factor_id, fd.factor_name, fd.factor_type
                ORDER BY record_count DESC
            """)
            
            stats = []
            for row in result.fetchall():
                stats.append({
                    'factor_id': row[0],
                    'factor_name': row[1],
                    'factor_type': row[2],
                    'record_count': row[3] or 0,
                    'date_range': f"{row[4]} 至 {row[5]}" if row[4] and row[5] else "无数据",
                    'avg_value': float(row[6]) if row[6] else 0,
                    'std_value': float(row[7]) if row[7] else 0
                })
            
            return stats
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_model_stats(self) -> List[Dict[str, Any]]:
        """获取模型统计信息"""
        try:
            models = MLModelDefinition.query.all()
            stats = []
            
            for model in models:
                # 获取预测记录数
                prediction_count = MLPredictions.query.filter_by(model_id=model.model_id).count()
                
                # 获取最新预测日期
                latest_prediction = MLPredictions.query.filter_by(model_id=model.model_id).order_by(MLPredictions.trade_date.desc()).first()
                latest_date = latest_prediction.trade_date if latest_prediction else None
                
                stats.append({
                    'model_id': model.model_id,
                    'model_name': model.model_name,
                    'model_type': model.model_type,
                    'factor_count': len(model.factor_list),
                    'prediction_count': prediction_count,
                    'latest_prediction_date': latest_date.strftime('%Y-%m-%d') if latest_date else "无预测",
                    'is_active': model.is_active,
                    'created_at': model.created_at.strftime('%Y-%m-%d') if model.created_at else ""
                })
            
            return stats
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_recent_predictions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的预测结果"""
        try:
            predictions = MLPredictions.query.order_by(MLPredictions.created_at.desc()).limit(limit).all()
            
            result = []
            for pred in predictions:
                # 获取股票名称
                stock = StockBasic.query.filter_by(ts_code=pred.ts_code).first()
                stock_name = stock.name if stock else "未知"
                
                result.append({
                    'ts_code': pred.ts_code,
                    'stock_name': stock_name,
                    'trade_date': pred.trade_date.strftime('%Y-%m-%d'),
                    'model_id': pred.model_id,
                    'predicted_return': float(pred.predicted_return) if pred.predicted_return else 0,
                    'probability_score': float(pred.probability_score) if pred.probability_score else 0,
                    'rank_score': pred.rank_score,
                    'created_at': pred.created_at.strftime('%Y-%m-%d %H:%M:%S') if pred.created_at else ""
                })
            
            return result
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_latest_factor_date(self) -> str:
        """获取最新因子数据日期"""
        try:
            latest = FactorValues.query.order_by(FactorValues.trade_date.desc()).first()
            return latest.trade_date.strftime('%Y-%m-%d') if latest else "无数据"
        except:
            return "无数据"
    
    def get_latest_prediction_date(self) -> str:
        """获取最新预测日期"""
        try:
            latest = MLPredictions.query.order_by(MLPredictions.trade_date.desc()).first()
            return latest.trade_date.strftime('%Y-%m-%d') if latest else "无数据"
        except:
            return "无数据"
    
    def calculate_factors(self, factor_ids: List[str], trade_date: str) -> Dict[str, Any]:
        """计算因子"""
        try:
            # 这里应该调用因子计算引擎
            # 暂时返回模拟结果
            result = {
                'calculated_factors': factor_ids,
                'trade_date': trade_date,
                'status': 'success',
                'message': f'已计算 {len(factor_ids)} 个因子'
            }
            return result
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def predict_with_model(self, model_id: str, trade_date: str, top_n: int) -> List[Dict[str, Any]]:
        """使用模型进行预测"""
        try:
            # 这里应该调用模型预测引擎
            # 暂时返回模拟结果
            predictions = []
            for i in range(min(top_n, 10)):
                predictions.append({
                    'ts_code': f'00000{i}.SZ',
                    'predicted_return': np.random.normal(0, 0.02),
                    'rank': i + 1
                })
            
            return predictions
        except Exception as e:
            return [{'error': str(e)}]
    
    def run(self, host='0.0.0.0', port=5001, debug=False):
        """运行Web应用"""
        print(f"🌐 启动多因子模型Web界面")
        print(f"   地址: http://{host}:{port}")
        print(f"   调试模式: {debug}")
        
        self.app.run(host=host, port=port, debug=debug)


def create_templates():
    """创建HTML模板文件"""
    
    # 确保模板目录存在
    template_dir = "templates"
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
    
    # 基础模板
    base_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}多因子模型系统{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar {
            min-height: 100vh;
            background-color: #f8f9fa;
        }
        .main-content {
            padding: 20px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .factor-card {
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            transition: box-shadow 0.3s;
        }
        .factor-card:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <!-- 侧边栏 -->
            <nav class="col-md-2 sidebar">
                <div class="position-sticky pt-3">
                    <h5 class="text-center mb-4">多因子模型系统</h5>
                    <ul class="nav flex-column">
                        <li class="nav-item">
                            <a class="nav-link" href="/dashboard">
                                <i class="bi bi-speedometer2"></i> 仪表板
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="/factors">
                                <i class="bi bi-calculator"></i> 因子管理
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="/models">
                                <i class="bi bi-cpu"></i> 模型管理
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="/predictions">
                                <i class="bi bi-graph-up"></i> 预测结果
                            </a>
                        </li>
                    </ul>
                </div>
            </nav>
            
            <!-- 主内容区 -->
            <main class="col-md-10 main-content">
                {% block content %}{% endblock %}
            </main>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
"""
    
    # 仪表板模板
    dashboard_template = """
{% extends "base.html" %}

{% block title %}仪表板 - 多因子模型系统{% endblock %}

{% block content %}
<div class="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center pt-3 pb-2 mb-3 border-bottom">
    <h1 class="h2">系统仪表板</h1>
    <div class="btn-toolbar mb-2 mb-md-0">
        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="refreshData()">
            <i class="bi bi-arrow-clockwise"></i> 刷新
        </button>
    </div>
</div>

<!-- 统计卡片 -->
<div class="row">
    <div class="col-md-3">
        <div class="stat-card">
            <h5><i class="bi bi-building"></i> 股票数量</h5>
            <h2>{{ stats.data_stats.stock_count | default(0) }}</h2>
        </div>
    </div>
    <div class="col-md-3">
        <div class="stat-card">
            <h5><i class="bi bi-graph-up"></i> 历史记录</h5>
            <h2>{{ "{:,}".format(stats.data_stats.history_records | default(0)) }}</h2>
        </div>
    </div>
    <div class="col-md-3">
        <div class="stat-card">
            <h5><i class="bi bi-calculator"></i> 因子记录</h5>
            <h2>{{ "{:,}".format(stats.data_stats.factor_records | default(0)) }}</h2>
        </div>
    </div>
    <div class="col-md-3">
        <div class="stat-card">
            <h5><i class="bi bi-cpu"></i> 活跃模型</h5>
            <h2>{{ stats.recent_activity.active_models | default(0) }}</h2>
        </div>
    </div>
</div>

<!-- 系统状态 -->
<div class="row mt-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5><i class="bi bi-info-circle"></i> 系统状态</h5>
            </div>
            <div class="card-body">
                <table class="table table-sm">
                    <tr>
                        <td>最新因子日期</td>
                        <td><span class="badge bg-primary">{{ stats.recent_activity.latest_factor_date }}</span></td>
                    </tr>
                    <tr>
                        <td>最新预测日期</td>
                        <td><span class="badge bg-success">{{ stats.recent_activity.latest_prediction_date }}</span></td>
                    </tr>
                    <tr>
                        <td>因子定义数量</td>
                        <td>{{ stats.data_stats.factor_definitions }}</td>
                    </tr>
                    <tr>
                        <td>模型定义数量</td>
                        <td>{{ stats.data_stats.model_definitions }}</td>
                    </tr>
                </table>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5><i class="bi bi-clock-history"></i> 最近活动</h5>
            </div>
            <div class="card-body">
                <p class="text-muted">系统运行正常</p>
                <p><small>最后更新: {{ stats.timestamp }}</small></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
function refreshData() {
    location.reload();
}
</script>
{% endblock %}
"""
    
    # 保存模板文件
    with open(f"{template_dir}/base.html", 'w', encoding='utf-8') as f:
        f.write(base_template)
    
    with open(f"{template_dir}/dashboard.html", 'w', encoding='utf-8') as f:
        f.write(dashboard_template)
    
    # 创建其他简化模板
    simple_templates = {
        'multifactor_dashboard.html': '''
{% extends "base.html" %}
{% block content %}
<div class="text-center mt-5">
    <h1>多因子模型系统</h1>
    <p class="lead">欢迎使用多因子选股和机器学习模型系统</p>
    <a href="/dashboard" class="btn btn-primary btn-lg">进入仪表板</a>
</div>
{% endblock %}
''',
        'factors.html': '''
{% extends "base.html" %}
{% block content %}
<h1>因子管理</h1>
<p>因子管理功能正在开发中...</p>
{% endblock %}
''',
        'models.html': '''
{% extends "base.html" %}
{% block content %}
<h1>模型管理</h1>
<p>模型管理功能正在开发中...</p>
{% endblock %}
''',
        'predictions.html': '''
{% extends "base.html" %}
{% block content %}
<h1>预测结果</h1>
<p>预测结果展示功能正在开发中...</p>
{% endblock %}
''',
        'error.html': '''
{% extends "base.html" %}
{% block content %}
<div class="alert alert-danger">
    <h4>系统错误</h4>
    <p>{{ error }}</p>
</div>
{% endblock %}
'''
    }
    
    for filename, content in simple_templates.items():
        with open(f"{template_dir}/{filename}", 'w', encoding='utf-8') as f:
            f.write(content)
    
    print(f"✅ HTML模板文件已创建在 {template_dir}/ 目录")


def main():
    """主函数"""
    print("🌐 多因子模型系统Web界面")
    print("="*50)
    
    # 创建模板文件
    create_templates()
    
    # 创建Web界面实例
    web_interface = MultifactorWebInterface()
    
    # 启动Web服务
    try:
        web_interface.run(host='0.0.0.0', port=5001, debug=True)
    except KeyboardInterrupt:
        print("\n👋 Web服务已停止")
    except Exception as e:
        print(f"❌ Web服务启动失败: {e}")


if __name__ == "__main__":
    main() 