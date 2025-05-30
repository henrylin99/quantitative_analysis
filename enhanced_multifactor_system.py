#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强的多因子模型系统
解决数据缺失和模型训练问题的完整解决方案

主要功能：
1. 批量计算历史因子数据
2. 修复数据匹配问题
3. 提供完整的机器学习训练流程
4. 包含数据验证和错误处理
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 机器学习库
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import train_test_split, cross_val_score, TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.feature_selection import SelectKBest, f_regression
import xgboost as xgb
import lightgbm as lgb

# 可视化库
import matplotlib.pyplot as plt
import seaborn as sns
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 数据库相关
from app import create_app
from app.extensions import db
from app.models import (
    StockDailyHistory, StockDailyBasic, StockFactor, StockMoneyflow, 
    StockCyqPerf, FactorDefinition, FactorValues, MLModelDefinition, 
    MLPredictions, StockBasic
)
from app.services.factor_engine import FactorEngine
from app.services.ml_models import MLModelManager

class EnhancedMultiFactorSystem:
    """增强的多因子模型系统"""
    
    def __init__(self):
        self.app = create_app()
        self.factor_engine = None
        self.ml_manager = None
        self.evaluation_results = {}
        
        print("🚀 初始化增强多因子模型系统...")
        print("=" * 80)
        
    def initialize_services(self):
        """初始化服务"""
        with self.app.app_context():
            self.factor_engine = FactorEngine()
            self.ml_manager = MLModelManager()
            print("✅ 服务初始化完成")
    
    def diagnose_data_issues(self):
        """诊断数据问题"""
        print("\n🔍 诊断数据问题...")
        print("=" * 60)
        
        with self.app.app_context():
            try:
                # 检查基础数据
                history_count = StockDailyHistory.query.count()
                basic_count = StockDailyBasic.query.count()
                factor_count = FactorValues.query.count()
                
                print(f"📊 数据统计:")
                print(f"   历史价格数据: {history_count:,} 条")
                print(f"   基本面数据: {basic_count:,} 条")
                print(f"   因子数据: {factor_count:,} 条")
                
                # 检查日期范围
                if history_count > 0:
                    min_date = db.session.query(db.func.min(StockDailyHistory.trade_date)).scalar()
                    max_date = db.session.query(db.func.max(StockDailyHistory.trade_date)).scalar()
                    print(f"   价格数据日期范围: {min_date} 至 {max_date}")
                
                if factor_count > 0:
                    factor_min_date = db.session.query(db.func.min(FactorValues.trade_date)).scalar()
                    factor_max_date = db.session.query(db.func.max(FactorValues.trade_date)).scalar()
                    print(f"   因子数据日期范围: {factor_min_date} 至 {factor_max_date}")
                    
                    # 检查因子类型
                    factor_types = db.session.query(FactorValues.factor_id).distinct().all()
                    factor_ids = [f[0] for f in factor_types]
                    print(f"   可用因子: {factor_ids}")
                
                # 诊断问题 - 修改逻辑，更宽松的条件
                issues = []
                if factor_count < 10000:  # 需要更多因子数据
                    issues.append("因子数据不足，需要计算更多因子")
                if len(db.session.query(FactorValues.factor_id).distinct().all()) < 5:
                    issues.append("因子种类不足，需要计算更多类型的因子")
                
                if issues:
                    print(f"\n⚠️  发现问题: {', '.join(issues)}")
                    return False
                else:
                    print(f"\n✅ 数据检查通过")
                    return True
                    
            except Exception as e:
                print(f"❌ 诊断失败: {e}")
                return False
    
    def calculate_comprehensive_factors(self, start_date='2025-05-01', end_date='2025-05-23'):
        """计算全面的因子数据"""
        print(f"\n🔧 计算全面因子数据 ({start_date} 至 {end_date})...")
        print("=" * 60)
        
        with self.app.app_context():
            try:
                # 获取所有股票代码
                stocks = StockBasic.query.limit(100).all()  # 先处理100只股票
                ts_codes = [stock.ts_code for stock in stocks]
                print(f"📈 处理股票数量: {len(ts_codes)}")
                
                # 定义要计算的因子
                factors_to_calculate = [
                    'momentum_5d',      # 5日动量
                    'momentum_20d',     # 20日动量
                    'volatility_20d',   # 20日波动率
                    'volume_ratio_20d', # 成交量比率
                    'price_to_ma20',    # 价格相对MA20
                    'pe_percentile',    # PE百分位
                    'pb_percentile',    # PB百分位
                ]
                
                # 生成日期序列
                date_range = pd.date_range(start=start_date, end=end_date, freq='D')
                trading_dates = []
                
                # 筛选交易日
                for date in date_range:
                    date_str = date.strftime('%Y-%m-%d')
                    count = StockDailyHistory.query.filter_by(trade_date=date_str).count()
                    if count > 0:
                        trading_dates.append(date_str)
                
                print(f"📅 交易日数量: {len(trading_dates)}")
                
                total_calculated = 0
                
                # 按日期计算因子
                for trade_date in trading_dates:
                    print(f"\n📊 计算 {trade_date} 的因子...")
                    
                    for factor_id in factors_to_calculate:
                        try:
                            # 计算因子
                            result_df = self.factor_engine.calculate_factor(
                                factor_id, ts_codes, trade_date, trade_date
                            )
                            
                            if not result_df.empty:
                                # 保存因子值
                                success = self.factor_engine.save_factor_values(result_df)
                                if success:
                                    total_calculated += len(result_df)
                                    print(f"   ✅ {factor_id}: {len(result_df)} 条记录")
                                else:
                                    print(f"   ❌ {factor_id}: 保存失败")
                            else:
                                print(f"   ⚠️  {factor_id}: 无数据")
                                
                        except Exception as e:
                            print(f"   ❌ {factor_id}: 计算失败 - {e}")
                
                print(f"\n✅ 因子计算完成，共计算 {total_calculated} 条因子数据")
                return total_calculated > 0
                
            except Exception as e:
                print(f"❌ 因子计算失败: {e}")
                return False
    
    def create_enhanced_models(self):
        """创建增强的机器学习模型"""
        print(f"\n🤖 创建增强机器学习模型...")
        print("=" * 60)
        
        with self.app.app_context():
            try:
                # 检查可用因子
                available_factors = db.session.query(FactorValues.factor_id).distinct().all()
                factor_ids = [f[0] for f in available_factors]
                
                if len(factor_ids) < 2:
                    print(f"⚠️  可用因子不足 ({len(factor_ids)}个)，无法创建模型")
                    return False
                
                print(f"📊 可用因子: {factor_ids}")
                
                # 如果因子不足，创建简化模型
                if len(factor_ids) < 5:
                    print("⚠️  因子数量较少，创建简化演示模型")
                    model_configs = [
                        {
                            'model_id': 'simple_demo_model',
                            'model_name': '简化演示模型',
                            'model_type': 'random_forest',
                            'factor_list': factor_ids,
                            'target_type': 'simulated_return',  # 使用模拟目标变量
                            'model_params': {
                                'n_estimators': 50,
                                'max_depth': 5,
                                'min_samples_split': 10,
                                'random_state': 42
                            }
                        }
                    ]
                else:
                    # 模型配置
                    model_configs = [
                        {
                            'model_id': 'enhanced_rf_model',
                            'model_name': '增强随机森林模型',
                            'model_type': 'random_forest',
                            'factor_list': factor_ids,
                            'target_type': 'return_5d',
                            'model_params': {
                                'n_estimators': 100,
                                'max_depth': 10,
                                'min_samples_split': 5,
                                'random_state': 42
                            }
                        },
                        {
                            'model_id': 'enhanced_xgb_model',
                            'model_name': '增强XGBoost模型',
                            'model_type': 'xgboost',
                            'factor_list': factor_ids,
                            'target_type': 'return_5d',
                            'model_params': {
                                'n_estimators': 100,
                                'max_depth': 6,
                                'learning_rate': 0.1,
                                'random_state': 42
                            }
                        }
                    ]
                
                created_models = []
                
                for config in model_configs:
                    try:
                        # 删除已存在的模型
                        existing = MLModelDefinition.query.filter_by(model_id=config['model_id']).first()
                        if existing:
                            db.session.delete(existing)
                            db.session.commit()
                        
                        # 创建新模型
                        success = self.ml_manager.create_model_definition(**config)
                        if success:
                            created_models.append(config['model_id'])
                            print(f"   ✅ 创建模型: {config['model_name']}")
                        else:
                            print(f"   ❌ 创建模型失败: {config['model_name']}")
                            
                    except Exception as e:
                        print(f"   ❌ 创建模型异常: {config['model_name']} - {e}")
                
                print(f"\n✅ 成功创建 {len(created_models)} 个模型")
                return len(created_models) > 0
                
            except Exception as e:
                print(f"❌ 创建模型失败: {e}")
                return False
    
    def train_models_with_validation(self):
        """训练模型并进行验证"""
        print(f"\n🎯 训练模型并验证...")
        print("=" * 60)
        
        with self.app.app_context():
            try:
                # 获取所有模型
                models = MLModelDefinition.query.filter_by(is_active=True).all()
                
                if not models:
                    print("❌ 没有可用的模型定义")
                    return False
                
                training_results = {}
                
                for model in models:
                    print(f"\n🔄 训练模型: {model.model_name}")
                    
                    try:
                        # 检查数据可用性
                        factor_count = FactorValues.query.filter(
                            FactorValues.factor_id.in_(model.factor_list)
                        ).count()
                        
                        if factor_count < 100:
                            print(f"   ⚠️  数据不足 ({factor_count} 条)，跳过训练")
                            continue
                        
                        # 获取日期范围
                        min_date = db.session.query(db.func.min(FactorValues.trade_date)).scalar()
                        max_date = db.session.query(db.func.max(FactorValues.trade_date)).scalar()
                        
                        print(f"   📅 训练日期范围: {min_date} 至 {max_date}")
                        
                        # 训练模型
                        result = self.ml_manager.train_model(
                            model.model_id, str(min_date), str(max_date)
                        )
                        
                        if result['success']:
                            training_results[model.model_id] = result
                            print(f"   ✅ 训练成功")
                            print(f"   📊 样本数量: {result.get('sample_count', 'N/A')}")
                            print(f"   📈 R²分数: {result.get('metrics', {}).get('r2_score', 'N/A'):.4f}")
                        else:
                            print(f"   ❌ 训练失败: {result.get('error', '未知错误')}")
                            
                    except Exception as e:
                        print(f"   ❌ 训练异常: {e}")
                
                print(f"\n✅ 完成模型训练，成功训练 {len(training_results)} 个模型")
                self.evaluation_results = training_results
                return len(training_results) > 0
                
            except Exception as e:
                print(f"❌ 模型训练失败: {e}")
                return False
    
    def generate_predictions(self, trade_date='2025-05-23'):
        """生成预测结果"""
        print(f"\n🔮 生成预测结果 ({trade_date})...")
        print("=" * 60)
        
        with self.app.app_context():
            try:
                # 获取已训练的模型
                models = MLModelDefinition.query.filter_by(is_active=True).all()
                trained_models = []
                
                for model in models:
                    if model.model_id in self.evaluation_results:
                        trained_models.append(model)
                
                if not trained_models:
                    print("❌ 没有已训练的模型")
                    return False
                
                prediction_results = {}
                
                for model in trained_models:
                    print(f"\n🎯 生成预测: {model.model_name}")
                    
                    try:
                        # 生成预测
                        predictions_df = self.ml_manager.predict(model.model_id, trade_date)
                        
                        if not predictions_df.empty:
                            # 保存预测结果
                            success = self.ml_manager.save_predictions(predictions_df)
                            if success:
                                prediction_results[model.model_id] = predictions_df
                                print(f"   ✅ 预测成功: {len(predictions_df)} 只股票")
                                
                                # 显示前5名预测结果
                                top_5 = predictions_df.nlargest(5, 'predicted_return')
                                print(f"   📈 预测收益前5名:")
                                for _, row in top_5.iterrows():
                                    print(f"      {row['ts_code']}: {row['predicted_return']:.4f}")
                            else:
                                print(f"   ❌ 保存预测失败")
                        else:
                            print(f"   ⚠️  预测结果为空")
                            
                    except Exception as e:
                        print(f"   ❌ 预测异常: {e}")
                
                print(f"\n✅ 完成预测生成，成功预测 {len(prediction_results)} 个模型")
                return len(prediction_results) > 0
                
            except Exception as e:
                print(f"❌ 预测生成失败: {e}")
                return False
    
    def create_comprehensive_report(self):
        """创建综合报告"""
        print(f"\n📊 生成综合评估报告...")
        print("=" * 60)
        
        with self.app.app_context():
            try:
                report = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'data_summary': {},
                    'model_performance': {},
                    'predictions_summary': {}
                }
                
                # 数据摘要
                history_count = StockDailyHistory.query.count()
                factor_count = FactorValues.query.count()
                model_count = MLModelDefinition.query.filter_by(is_active=True).count()
                prediction_count = MLPredictions.query.count()
                
                report['data_summary'] = {
                    'history_records': history_count,
                    'factor_records': factor_count,
                    'active_models': model_count,
                    'prediction_records': prediction_count
                }
                
                # 模型性能
                for model_id, results in self.evaluation_results.items():
                    model = MLModelDefinition.query.filter_by(model_id=model_id).first()
                    if model:
                        report['model_performance'][model_id] = {
                            'model_name': model.model_name,
                            'model_type': model.model_type,
                            'success': results['success'],
                            'metrics': results.get('metrics', {}),
                            'sample_count': results.get('sample_count', 0)
                        }
                
                # 预测摘要
                latest_predictions = MLPredictions.query.order_by(
                    MLPredictions.trade_date.desc()
                ).limit(10).all()
                
                if latest_predictions:
                    report['predictions_summary'] = {
                        'latest_date': str(latest_predictions[0].trade_date),
                        'prediction_count': len(latest_predictions),
                        'top_predictions': [
                            {
                                'ts_code': pred.ts_code,
                                'predicted_return': float(pred.predicted_return),
                                'model_id': pred.model_id
                            }
                            for pred in latest_predictions[:5]
                        ]
                    }
                
                # 保存报告
                report_file = f"enhanced_multifactor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write("增强多因子模型系统评估报告\n")
                    f.write("=" * 50 + "\n\n")
                    
                    f.write(f"生成时间: {report['timestamp']}\n\n")
                    
                    f.write("数据摘要:\n")
                    for key, value in report['data_summary'].items():
                        f.write(f"  {key}: {value:,}\n")
                    f.write("\n")
                    
                    f.write("模型性能:\n")
                    for model_id, perf in report['model_performance'].items():
                        f.write(f"  {perf['model_name']} ({model_id}):\n")
                        f.write(f"    类型: {perf['model_type']}\n")
                        f.write(f"    训练状态: {'成功' if perf['success'] else '失败'}\n")
                        f.write(f"    样本数量: {perf['sample_count']:,}\n")
                        if perf['metrics']:
                            for metric, value in perf['metrics'].items():
                                if isinstance(value, (int, float)):
                                    f.write(f"    {metric}: {value:.4f}\n")
                        f.write("\n")
                    
                    if report['predictions_summary']:
                        f.write("预测摘要:\n")
                        f.write(f"  最新预测日期: {report['predictions_summary']['latest_date']}\n")
                        f.write(f"  预测数量: {report['predictions_summary']['prediction_count']}\n")
                        f.write("  预测收益前5名:\n")
                        for pred in report['predictions_summary']['top_predictions']:
                            f.write(f"    {pred['ts_code']}: {pred['predicted_return']:.4f}\n")
                
                print(f"✅ 报告已保存: {report_file}")
                
                # 控制台输出摘要
                print(f"\n📋 系统状态摘要:")
                print(f"   历史数据: {history_count:,} 条")
                print(f"   因子数据: {factor_count:,} 条")
                print(f"   活跃模型: {model_count} 个")
                print(f"   预测记录: {prediction_count:,} 条")
                print(f"   成功训练: {len(self.evaluation_results)} 个模型")
                
                return True
                
            except Exception as e:
                print(f"❌ 生成报告失败: {e}")
                return False
    
    def run_complete_pipeline(self):
        """运行完整的多因子模型流程"""
        print("🚀 启动增强多因子模型系统完整流程")
        print("=" * 80)
        
        try:
            # 1. 初始化服务
            self.initialize_services()
            
            # 2. 诊断数据问题
            data_ok = self.diagnose_data_issues()
            
            # 3. 计算因子数据（如果需要）
            if not data_ok:
                print("\n🔧 数据不足，开始计算因子数据...")
                factor_ok = self.calculate_comprehensive_factors()
                if not factor_ok:
                    print("❌ 因子计算失败，无法继续")
                    return False
            
            # 4. 创建模型
            model_ok = self.create_enhanced_models()
            if not model_ok:
                print("❌ 模型创建失败，无法继续")
                return False
            
            # 5. 训练模型
            train_ok = self.train_models_with_validation()
            if not train_ok:
                print("❌ 模型训练失败，无法继续")
                return False
            
            # 6. 生成预测
            pred_ok = self.generate_predictions()
            if not pred_ok:
                print("❌ 预测生成失败")
            
            # 7. 生成报告
            report_ok = self.create_comprehensive_report()
            
            print("\n🎉 增强多因子模型系统流程完成！")
            print("=" * 80)
            
            return True
            
        except Exception as e:
            print(f"❌ 流程执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """主函数"""
    system = EnhancedMultiFactorSystem()
    success = system.run_complete_pipeline()
    
    if success:
        print("\n✅ 系统运行成功！")
        print("💡 接下来可以:")
        print("   1. 查看生成的评估报告")
        print("   2. 在Web界面中查看模型和预测结果")
        print("   3. 继续优化模型参数")
    else:
        print("\n❌ 系统运行失败，请检查错误信息")

if __name__ == "__main__":
    main() 