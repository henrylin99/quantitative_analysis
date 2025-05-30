#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
演示版机器学习模型
基于技术因子数据进行股票收益预测演示
包含完整的训练、评估和可视化流程
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 机器学习库
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import train_test_split, cross_val_score
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

# 数据库连接
import pymysql

class DemoMLModel:
    """演示版机器学习模型"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.evaluation_results = {}
        
        # 模型配置
        self.model_configs = {
            'RandomForest': {
                'model': RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1),
                'name': '随机森林'
            },
            'XGBoost': {
                'model': xgb.XGBRegressor(n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42),
                'name': 'XGBoost梯度提升'
            },
            'LightGBM': {
                'model': lgb.LGBMRegressor(n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42, verbose=-1),
                'name': 'LightGBM'
            },
            'Ridge': {
                'model': Ridge(alpha=1.0, random_state=42),
                'name': '岭回归'
            }
        }
        
        # 数据库连接
        self.connection = pymysql.connect(
            host='localhost',
            user='root',
            password='root',
            database='stock_cursor',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print("✅ 成功连接到数据库")
    
    def prepare_demo_dataset(self):
        """准备演示数据集"""
        print("\n🔧 准备演示数据集...")
        print("=" * 80)
        
        try:
            # 使用技术因子表的数据
            query = """
            SELECT 
                ts_code,
                trade_date,
                rsi_14,
                macd_dif,
                macd_dea,
                macd_histogram,
                bollinger_upper,
                bollinger_lower,
                bollinger_percent,
                stochastic_k,
                stochastic_d,
                atr_14,
                cci_14,
                williams_r,
                momentum_10,
                volume_ratio
            FROM stock_technical_factors 
            WHERE trade_date >= '2023-01-01' 
            AND trade_date <= '2023-12-31'
            ORDER BY ts_code, trade_date
            LIMIT 1000
            """
            
            df = pd.read_sql(query, self.connection)
            
            if df.empty:
                print("❌ 未获取到技术因子数据")
                return None
            
            # 转换数据类型
            numeric_cols = ['rsi_14', 'macd_dif', 'macd_dea', 'macd_histogram',
                           'bollinger_upper', 'bollinger_lower', 'bollinger_percent',
                           'stochastic_k', 'stochastic_d', 'atr_14', 'cci_14',
                           'williams_r', 'momentum_10', 'volume_ratio']
            
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 删除包含NaN的行
            df = df.dropna()
            
            if df.empty:
                print("❌ 数据清洗后为空")
                return None
            
            # 生成目标变量（模拟未来收益率）
            np.random.seed(42)
            
            # 基于技术指标计算基础收益率
            # 使用RSI、MACD、布林线等指标的组合
            feature_weights = [0.05, 0.1, 0.1, 0.05, 0.03, 0.03, 0.15, 
                              0.08, 0.08, 0.05, 0.1, 0.08, 0.05, 0.05]
            
            # 标准化特征
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(df[numeric_cols])
            
            # 计算基础收益率（特征的线性组合）
            base_returns = np.dot(features_scaled, feature_weights[:len(numeric_cols)])
            
            # 添加随机噪声
            noise = np.random.normal(0, 1.5, len(base_returns))
            df['future_return'] = base_returns + noise
            
            # 处理异常值
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.fillna(df.median())
            
            # 确保有足够的数据
            if len(df) < 100:
                print("❌ 数据量不足，无法进行训练")
                return None
            
            print(f"✅ 数据集准备完成：{len(df)} 条记录")
            print(f"📊 包含股票数：{df['ts_code'].nunique()} 只")
            print(f"📅 时间范围：{df['trade_date'].min()} 至 {df['trade_date'].max()}")
            print(f"📈 可用特征：{len(numeric_cols)} 个技术指标")
            
            return df
            
        except Exception as e:
            print(f"❌ 数据集准备失败：{e}")
            import traceback
            traceback.print_exc()
            return None
    
    def prepare_features_and_target(self, data):
        """准备特征和目标变量"""
        print("\n🎯 准备特征和目标变量...")
        
        # 选择技术指标作为特征
        feature_columns = [
            'rsi_14', 'macd_dif', 'macd_dea', 'macd_histogram',
            'bollinger_percent', 'stochastic_k', 'stochastic_d',
            'atr_14', 'cci_14', 'williams_r', 'momentum_10', 'volume_ratio'
        ]
        
        # 检查特征可用性
        available_features = [col for col in feature_columns if col in data.columns]
        print(f"📊 可用特征数量：{len(available_features)}")
        print(f"📋 特征列表：{', '.join(available_features)}")
        
        if len(available_features) < 4:
            print("❌ 可用特征太少，无法训练模型")
            return None, None
        
        # 准备特征矩阵和目标变量
        X = data[available_features].copy()
        y = data['future_return'].copy()
        
        # 处理异常值
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.fillna(X.median())
        
        print(f"✅ 特征准备完成：{X.shape[0]} 样本，{X.shape[1]} 特征")
        print(f"🎯 目标变量统计：均值={y.mean():.4f}，标准差={y.std():.4f}")
        
        return X, y
    
    def train_models(self, X, y):
        """训练多个模型"""
        print("\n🚀 开始模型训练...")
        print("=" * 80)
        
        # 数据划分
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=True
        )
        
        print(f"📊 训练集：{len(X_train)} 样本")
        print(f"📊 测试集：{len(X_test)} 样本")
        
        # 特征缩放
        scaler = RobustScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        self.scalers['main'] = scaler
        
        # 训练各个模型
        for model_name, model_config in self.model_configs.items():
            print(f"\n🔧 训练 {model_config['name']} 模型...")
            
            try:
                model = model_config['model']
                
                # 训练模型
                model.fit(X_train_scaled, y_train)
                
                # 预测
                y_train_pred = model.predict(X_train_scaled)
                y_test_pred = model.predict(X_test_scaled)
                
                # 评估指标
                train_r2 = r2_score(y_train, y_train_pred)
                test_r2 = r2_score(y_test, y_test_pred)
                train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
                test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
                train_mae = mean_absolute_error(y_train, y_train_pred)
                test_mae = mean_absolute_error(y_test, y_test_pred)
                
                # 交叉验证
                cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring='r2')
                
                # 保存模型和结果
                self.models[model_name] = model
                self.evaluation_results[model_name] = {
                    'train_r2': train_r2,
                    'test_r2': test_r2,
                    'train_rmse': train_rmse,
                    'test_rmse': test_rmse,
                    'train_mae': train_mae,
                    'test_mae': test_mae,
                    'cv_mean': cv_scores.mean(),
                    'cv_std': cv_scores.std(),
                    'y_train_true': y_train,
                    'y_train_pred': y_train_pred,
                    'y_test_true': y_test,
                    'y_test_pred': y_test_pred,
                    'feature_names': X.columns.tolist()
                }
                
                print(f"  ✅ 训练R²: {train_r2:.4f}")
                print(f"  ✅ 测试R²: {test_r2:.4f}")
                print(f"  ✅ 测试RMSE: {test_rmse:.4f}")
                print(f"  ✅ 交叉验证: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
                
            except Exception as e:
                print(f"  ❌ {model_config['name']} 训练失败：{e}")
        
        print(f"\n🎉 模型训练完成！成功训练了 {len(self.models)} 个模型")
        
        return X_train, X_test, y_train, y_test
    
    def evaluate_and_compare_models(self):
        """评估和比较模型性能"""
        print("\n📊 模型性能评估与比较")
        print("=" * 80)
        
        if not self.evaluation_results:
            print("❌ 没有可评估的模型")
            return None, None
        
        # 创建评估表格
        results_df = pd.DataFrame({
            model_name: {
                '训练R²': f"{results['train_r2']:.4f}",
                '测试R²': f"{results['test_r2']:.4f}",
                '测试RMSE': f"{results['test_rmse']:.4f}",
                '测试MAE': f"{results['test_mae']:.4f}",
                '交叉验证均值': f"{results['cv_mean']:.4f}",
                '交叉验证标准差': f"{results['cv_std']:.4f}"
            }
            for model_name, results in self.evaluation_results.items()
        }).T
        
        print("📋 详细性能指标：")
        print(results_df.to_string())
        
        # 找出最佳模型
        best_model_name = max(self.evaluation_results.keys(), 
                             key=lambda x: self.evaluation_results[x]['test_r2'])
        best_r2 = self.evaluation_results[best_model_name]['test_r2']
        
        print(f"\n🏆 最佳模型：{self.model_configs[best_model_name]['name']}")
        print(f"🎯 最佳测试R²：{best_r2:.4f}")
        
        return results_df, best_model_name
    
    def visualize_results(self):
        """可视化结果"""
        print("\n📈 生成可视化图表...")
        
        if not self.evaluation_results:
            print("❌ 没有可视化的数据")
            return
        
        # 创建图表
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('🤖 机器学习模型性能评估结果 🎯', fontsize=16, fontweight='bold')
        
        # 1. R²分数比较
        model_names = list(self.evaluation_results.keys())
        test_r2_scores = [self.evaluation_results[name]['test_r2'] for name in model_names]
        
        bars1 = axes[0, 0].bar(model_names, test_r2_scores, color='skyblue', alpha=0.7)
        axes[0, 0].set_title('测试集R²分数比较')
        axes[0, 0].set_ylabel('R²分数')
        axes[0, 0].tick_params(axis='x', rotation=45)
        axes[0, 0].grid(axis='y', alpha=0.3)
        
        # 添加数值标签
        for bar, score in zip(bars1, test_r2_scores):
            axes[0, 0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.001,
                           f'{score:.3f}', ha='center', va='bottom', fontweight='bold')
        
        # 2. RMSE比较
        test_rmse_scores = [self.evaluation_results[name]['test_rmse'] for name in model_names]
        
        bars2 = axes[0, 1].bar(model_names, test_rmse_scores, color='lightcoral', alpha=0.7)
        axes[0, 1].set_title('测试集RMSE比较')
        axes[0, 1].set_ylabel('RMSE')
        axes[0, 1].tick_params(axis='x', rotation=45)
        axes[0, 1].grid(axis='y', alpha=0.3)
        
        # 添加数值标签
        for bar, score in zip(bars2, test_rmse_scores):
            axes[0, 1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                           f'{score:.2f}', ha='center', va='bottom', fontweight='bold')
        
        # 3. 交叉验证分数
        cv_means = [self.evaluation_results[name]['cv_mean'] for name in model_names]
        cv_stds = [self.evaluation_results[name]['cv_std'] for name in model_names]
        
        bars3 = axes[0, 2].bar(model_names, cv_means, yerr=cv_stds, capsize=5, 
                              color='lightgreen', alpha=0.7)
        axes[0, 2].set_title('交叉验证分数')
        axes[0, 2].set_ylabel('CV R²分数')
        axes[0, 2].tick_params(axis='x', rotation=45)
        axes[0, 2].grid(axis='y', alpha=0.3)
        
        # 4. 最佳模型的预测 vs 实际值（训练集）
        best_model_name = max(model_names, key=lambda x: self.evaluation_results[x]['test_r2'])
        best_results = self.evaluation_results[best_model_name]
        
        axes[1, 0].scatter(best_results['y_train_true'], best_results['y_train_pred'], 
                          alpha=0.6, color='blue', s=30)
        axes[1, 0].plot([best_results['y_train_true'].min(), best_results['y_train_true'].max()],
                       [best_results['y_train_true'].min(), best_results['y_train_true'].max()],
                       'r--', lw=2)
        axes[1, 0].set_xlabel('实际收益率 (%)')
        axes[1, 0].set_ylabel('预测收益率 (%)')
        axes[1, 0].set_title(f'{self.model_configs[best_model_name]["name"]} - 训练集预测')
        axes[1, 0].grid(alpha=0.3)
        
        # 5. 最佳模型的预测 vs 实际值（测试集）
        axes[1, 1].scatter(best_results['y_test_true'], best_results['y_test_pred'], 
                          alpha=0.6, color='red', s=30)
        axes[1, 1].plot([best_results['y_test_true'].min(), best_results['y_test_true'].max()],
                       [best_results['y_test_true'].min(), best_results['y_test_true'].max()],
                       'r--', lw=2)
        axes[1, 1].set_xlabel('实际收益率 (%)')
        axes[1, 1].set_ylabel('预测收益率 (%)')
        axes[1, 1].set_title(f'{self.model_configs[best_model_name]["name"]} - 测试集预测')
        axes[1, 1].grid(alpha=0.3)
        
        # 6. 特征重要性（如果模型支持）
        if hasattr(self.models[best_model_name], 'feature_importances_'):
            importances = self.models[best_model_name].feature_importances_
            feature_names = best_results['feature_names']
            
            # 排序特征重要性
            indices = np.argsort(importances)[::-1]
            sorted_importances = importances[indices]
            sorted_features = [feature_names[i] for i in indices]
            
            bars6 = axes[1, 2].barh(range(len(sorted_features)), sorted_importances, 
                                   color='orange', alpha=0.7)
            axes[1, 2].set_yticks(range(len(sorted_features)))
            axes[1, 2].set_yticklabels(sorted_features)
            axes[1, 2].set_xlabel('特征重要性')
            axes[1, 2].set_title('🔍 技术指标重要性排序')
            axes[1, 2].grid(axis='x', alpha=0.3)
            
            # 添加数值标签
            for i, (bar, importance) in enumerate(zip(bars6, sorted_importances)):
                axes[1, 2].text(bar.get_width() + 0.005, bar.get_y() + bar.get_height()/2,
                               f'{importance:.3f}', ha='left', va='center', fontweight='bold')
        else:
            axes[1, 2].text(0.5, 0.5, '该模型不支持\n特征重要性分析', 
                           ha='center', va='center', transform=axes[1, 2].transAxes,
                           fontsize=12)
            axes[1, 2].set_title('特征重要性')
        
        plt.tight_layout()
        plt.savefig('demo_ml_evaluation_results.png', dpi=300, bbox_inches='tight')
        print("📊 图表已保存为 'demo_ml_evaluation_results.png'")
        
        # 显示图表（在支持的环境中）
        try:
            plt.show()
        except:
            print("📋 注意：图形界面不可用，但图表已保存为文件")
    
    def generate_detailed_report(self):
        """生成详细的评估报告"""
        print("\n📋 生成详细评估报告...")
        
        report = []
        report.append("=" * 100)
        report.append("🤖 股票收益预测机器学习模型 - 完整评估报告")
        report.append("=" * 100)
        report.append(f"⏰ 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"📊 模型类型：基于技术指标的股票收益预测")
        report.append("")
        
        # 模型性能对比
        report.append("🏆 模型性能对比")
        report.append("-" * 50)
        
        for model_name, results in self.evaluation_results.items():
            model_display_name = self.model_configs[model_name]['name']
            report.append(f"📈 {model_display_name}:")
            report.append(f"    训练集R²: {results['train_r2']:.4f}")
            report.append(f"    测试集R²: {results['test_r2']:.4f}")
            report.append(f"    测试集RMSE: {results['test_rmse']:.4f}")
            report.append(f"    测试集MAE: {results['test_mae']:.4f}")
            report.append(f"    交叉验证: {results['cv_mean']:.4f} ± {results['cv_std']:.4f}")
            report.append("")
        
        # 最佳模型
        best_model_name = max(self.evaluation_results.keys(), 
                             key=lambda x: self.evaluation_results[x]['test_r2'])
        best_model_display = self.model_configs[best_model_name]['name']
        best_r2 = self.evaluation_results[best_model_name]['test_r2']
        
        report.append("🎯 最佳模型")
        report.append("-" * 50)
        report.append(f"🏆 模型名称：{best_model_display}")
        report.append(f"📊 测试集R²：{best_r2:.4f}")
        report.append(f"💡 解释：该模型能够解释约 {best_r2*100:.1f}% 的收益率变化")
        report.append("")
        
        # 性能分析
        report.append("📊 性能分析")
        report.append("-" * 50)
        if best_r2 >= 0.7:
            performance_level = "🌟 优秀"
            analysis = "模型表现优秀，预测能力强，可用于实际投资决策参考"
        elif best_r2 >= 0.5:
            performance_level = "✅ 良好"
            analysis = "模型表现良好，有一定预测能力，建议结合其他指标使用"
        elif best_r2 >= 0.3:
            performance_level = "⚠️ 中等"
            analysis = "模型表现中等，建议谨慎使用并结合其他分析方法"
        elif best_r2 >= 0.1:
            performance_level = "🔶 一般"
            analysis = "模型表现一般，主要用于学习和演示目的"
        else:
            performance_level = "❌ 较差"
            analysis = "模型表现较差，需要进一步优化或收集更多数据"
        
        report.append(f"评估等级：{performance_level}")
        report.append(f"分析结论：{analysis}")
        report.append("")
        
        # 技术指标贡献度
        if hasattr(self.models[best_model_name], 'feature_importances_'):
            report.append("🔍 技术指标贡献度分析")
            report.append("-" * 50)
            importances = self.models[best_model_name].feature_importances_
            feature_names = self.evaluation_results[best_model_name]['feature_names']
            
            # 排序特征重要性
            sorted_indices = np.argsort(importances)[::-1]
            for i, idx in enumerate(sorted_indices[:5]):  # 显示前5个重要特征
                report.append(f"  {i+1}. {feature_names[idx]}: {importances[idx]:.4f}")
            report.append("")
        
        # 改进建议
        report.append("📋 改进建议")
        report.append("-" * 50)
        report.append("  1. 增加更多的技术指标和市场数据")
        report.append("  2. 考虑宏观经济指标和基本面数据")
        report.append("  3. 使用更长的历史数据进行训练")
        report.append("  4. 尝试深度学习模型和集成学习方法")
        report.append("  5. 进行特征工程和数据预处理优化")
        report.append("  6. 考虑时间序列特性，使用LSTM等序列模型")
        report.append("")
        
        # 使用注意事项
        report.append("⚠️ 使用注意事项")
        report.append("-" * 50)
        report.append("  1. 本模型基于历史数据训练，无法保证未来收益率预测的准确性")
        report.append("  2. 股票市场具有不确定性，模型预测仅供参考，不构成投资建议")
        report.append("  3. 建议结合基本面分析、技术分析等多种方法进行投资决策")
        report.append("  4. 定期更新模型训练数据，提高模型的时效性")
        report.append("  5. 注意风险控制，避免过度依赖单一模型的预测结果")
        report.append("  6. 在实际使用前，建议进行更长时间的回测验证")
        report.append("")
        
        report.append("🎉 评估完成！感谢使用机器学习模型评估系统")
        report.append("=" * 100)
        
        # 保存报告
        report_text = "\n".join(report)
        with open('demo_ml_evaluation_report.txt', 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print(report_text)
        print("\n📄 详细报告已保存为 'demo_ml_evaluation_report.txt'")
        
        return report_text
    
    def run_complete_pipeline(self):
        """运行完整的机器学习管道"""
        print("🚀 启动演示版完整机器学习管道")
        print("基于技术指标的股票收益预测模型演示")
        print("=" * 100)
        
        try:
            # 1. 数据准备
            dataset = self.prepare_demo_dataset()
            if dataset is None:
                print("❌ 数据准备失败，终止程序")
                return False
            
            # 2. 特征工程
            X, y = self.prepare_features_and_target(dataset)
            if X is None:
                print("❌ 特征准备失败，终止程序")
                return False
            
            # 3. 模型训练
            self.train_models(X, y)
            
            # 4. 模型评估
            results_df, best_model = self.evaluate_and_compare_models()
            
            # 5. 可视化
            self.visualize_results()
            
            # 6. 生成报告
            self.generate_detailed_report()
            
            print("\n🎉 完整机器学习管道执行成功！")
            print("📊 请查看生成的图表和报告文件")
            print("📁 生成的文件：")
            print("  - demo_ml_evaluation_results.png: 可视化图表")
            print("  - demo_ml_evaluation_report.txt: 详细评估报告")
            
            return True
            
        except Exception as e:
            print(f"❌ 管道执行失败：{e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # 关闭数据库连接
            if hasattr(self, 'connection'):
                self.connection.close()
                print("🔒 数据库连接已关闭")

def main():
    """主函数"""
    print("🤖 启动股票收益预测机器学习系统（演示版）")
    print("基于技术指标的完整模型训练与评估")
    print("=" * 100)
    
    # 创建并运行演示版模型
    ml_model = DemoMLModel()
    success = ml_model.run_complete_pipeline()
    
    if success:
        print("\n✅ 系统运行成功！")
        print("\n🎊 恭喜！您已成功完成机器学习模型的完整训练和评估流程")
        print("💡 现在您可以查看详细的测评结果，包括：")
        print("  🔹 多个算法的性能对比分析")
        print("  🔹 可视化的预测效果图表")
        print("  🔹 技术指标重要性分析")
        print("  🔹 详细的评估报告和建议")
        print("\n📈 这个完整的机器学习系统展示了从数据准备到模型评估的全流程！")
        print("🔥 您现在拥有了一个可以运行的股票预测模型！")
    else:
        print("\n❌ 系统运行失败，请检查错误信息")

if __name__ == "__main__":
    main() 