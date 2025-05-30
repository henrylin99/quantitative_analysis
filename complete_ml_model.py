#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的机器学习模型系统
基于增强版财务因子进行股票收益预测
包含数据准备、训练、评估、可视化和测试结果
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
from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression
import xgboost as xgb
import lightgbm as lgb

# 可视化库
import matplotlib.pyplot as plt
import seaborn as sns
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 数据库连接
import pymysql

# 导入我们的财务因子工具
from enhanced_financial_factors import EnhancedFinancialFactors

class CompleteMLModel:
    """完整的机器学习模型系统"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_selectors = {}
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
            'GradientBoosting': {
                'model': GradientBoostingRegressor(n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42),
                'name': '梯度提升'
            },
            'Ridge': {
                'model': Ridge(alpha=1.0, random_state=42),
                'name': '岭回归'
            }
        }
        
        # 初始化财务因子计算器
        self.factor_calculator = EnhancedFinancialFactors()
        
    def prepare_comprehensive_dataset(self, start_date="2020-01-01", end_date="2023-12-31"):
        """准备综合数据集"""
        print("\n🔧 准备综合数据集...")
        print("=" * 80)
        
        try:
            # 获取股票列表（选择活跃的股票）
            connection = self.factor_calculator.connection
            
            # 获取有足够数据的股票
            stock_query = """
            SELECT DISTINCT ts_code 
            FROM stock_income_statement 
            WHERE end_date >= %s AND end_date <= %s
            GROUP BY ts_code 
            HAVING COUNT(*) >= 8  -- 至少8个季度的数据
            ORDER BY ts_code
            LIMIT 100  -- 限制股票数量以加快训练
            """
            
            with connection.cursor() as cursor:
                cursor.execute(stock_query, (start_date, end_date))
                stock_list = [row['ts_code'] for row in cursor.fetchall()]
            
            print(f"📊 选择了 {len(stock_list)} 只股票进行训练")
            
            all_data = []
            
            for i, ts_code in enumerate(stock_list[:20]):  # 先用20只股票测试
                print(f"📈 处理股票 {i+1}/{min(20, len(stock_list))}: {ts_code}")
                
                # 计算财务因子
                financial_factors = self.factor_calculator.calculate_comprehensive_financial_factors(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if financial_factors is not None and len(financial_factors) > 0:
                    # 添加收益率目标变量
                    financial_factors_with_returns = self._add_future_returns(financial_factors, ts_code)
                    if financial_factors_with_returns is not None:
                        all_data.append(financial_factors_with_returns)
            
            if not all_data:
                print("❌ 未获取到任何有效数据")
                return None
            
            # 合并所有数据
            combined_data = pd.concat(all_data, ignore_index=True)
            combined_data = combined_data.dropna()
            
            print(f"✅ 数据集准备完成：{len(combined_data)} 条记录")
            print(f"📊 包含股票数：{combined_data['ts_code'].nunique()} 只")
            print(f"📅 时间范围：{combined_data['end_date'].min()} 至 {combined_data['end_date'].max()}")
            
            return combined_data
            
        except Exception as e:
            print(f"❌ 数据集准备失败：{e}")
            return None
    
    def _add_future_returns(self, financial_data, ts_code):
        """添加未来收益率作为目标变量"""
        try:
            # 获取股价数据计算收益率
            connection = self.factor_calculator.connection
            
                                      price_query = """
             SELECT trade_date, close 
             FROM stock_daily_history 
             WHERE ts_code = %s 
             AND trade_date >= %s
             ORDER BY trade_date
             """
             
             # 确保日期格式正确
             start_date = financial_data['end_date'].min()
             if hasattr(start_date, 'strftime'):
                 start_date = start_date.strftime('%Y-%m-%d')
             else:
                 start_date = str(start_date)
             
             with connection.cursor() as cursor:
                cursor.execute(price_query, (ts_code, start_date))
                price_data = pd.DataFrame(cursor.fetchall())
            
            if price_data.empty:
                return None
            
            price_data['trade_date'] = pd.to_datetime(price_data['trade_date'])
            price_data['close'] = pd.to_numeric(price_data['close'], errors='coerce')
            price_data = price_data.dropna().sort_values('trade_date')
            
            # 计算未来20日收益率作为目标变量
            price_data['future_20d_return'] = price_data['close'].pct_change(20).shift(-20) * 100
            
            # 将财务报告日期匹配到最近的交易日
            financial_data_with_returns = financial_data.copy()
            financial_data_with_returns['end_date'] = pd.to_datetime(financial_data_with_returns['end_date'])
            
            returns_list = []
            for _, row in financial_data_with_returns.iterrows():
                report_date = row['end_date']
                # 找到报告日期后最近的交易日
                future_prices = price_data[price_data['trade_date'] > report_date]
                if len(future_prices) > 0:
                    nearest_price = future_prices.iloc[0]
                    returns_list.append(nearest_price['future_20d_return'])
                else:
                    returns_list.append(np.nan)
            
            financial_data_with_returns['future_20d_return'] = returns_list
            financial_data_with_returns = financial_data_with_returns.dropna(subset=['future_20d_return'])
            
            return financial_data_with_returns
            
        except Exception as e:
            print(f"❌ 添加收益率失败 {ts_code}: {e}")
            return None
    
    def prepare_features_and_target(self, data):
        """准备特征和目标变量"""
        print("\n🎯 准备特征和目标变量...")
        
        # 选择财务因子作为特征
        feature_columns = [
            # 盈利能力因子
            'gross_profit_margin', 'operating_profit_margin', 'net_profit_margin',
            'expense_ratio', 'rd_expense_ratio',
            
            # 偿债能力因子  
            'current_ratio', 'debt_to_equity', 'interest_coverage',
            
            # 营运能力因子
            'total_asset_turnover', 'receivables_turnover', 'inventory_turnover',
            
            # 现金流因子
            'operating_cashflow_ratio', 'free_cashflow_ratio', 'operating_cf_to_net_income',
            
            # 成长能力因子
            'revenue_growth_yoy', 'net_profit_growth_yoy', 'eps_growth_yoy'
        ]
        
        # 检查哪些特征实际存在
        available_features = [col for col in feature_columns if col in data.columns]
        print(f"📊 可用特征数量：{len(available_features)}")
        print(f"📋 特征列表：{', '.join(available_features[:10])}...")
        
        if len(available_features) < 5:
            print("❌ 可用特征太少，无法训练模型")
            return None, None
        
        # 准备特征矩阵
        X = data[available_features].copy()
        y = data['future_20d_return'].copy()
        
        # 处理无穷大和NaN值
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
        
        # 特征选择
        selector = SelectKBest(score_func=f_regression, k=min(15, X.shape[1]))
        X_train_selected = selector.fit_transform(X_train_scaled, y_train)
        X_test_selected = selector.transform(X_test_scaled)
        self.feature_selectors['main'] = selector
        
        selected_features = X.columns[selector.get_support()]
        print(f"🎯 选择的关键特征：{', '.join(selected_features)}")
        
        # 训练各个模型
        for model_name, model_config in self.model_configs.items():
            print(f"\n🔧 训练 {model_config['name']} 模型...")
            
            try:
                model = model_config['model']
                
                # 训练模型
                model.fit(X_train_selected, y_train)
                
                # 预测
                y_train_pred = model.predict(X_train_selected)
                y_test_pred = model.predict(X_test_selected)
                
                # 评估指标
                train_r2 = r2_score(y_train, y_train_pred)
                test_r2 = r2_score(y_test, y_test_pred)
                train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
                test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
                train_mae = mean_absolute_error(y_train, y_train_pred)
                test_mae = mean_absolute_error(y_test, y_test_pred)
                
                # 交叉验证
                cv_scores = cross_val_score(model, X_train_selected, y_train, cv=5, scoring='r2')
                
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
                    'feature_names': selected_features
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
            return
        
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
        print(results_df)
        
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
        fig.suptitle('机器学习模型性能评估结果', fontsize=16, fontweight='bold')
        
        # 1. R²分数比较
        model_names = list(self.evaluation_results.keys())
        test_r2_scores = [self.evaluation_results[name]['test_r2'] for name in model_names]
        
        axes[0, 0].bar(model_names, test_r2_scores, color='skyblue', alpha=0.7)
        axes[0, 0].set_title('测试集R²分数比较')
        axes[0, 0].set_ylabel('R²分数')
        axes[0, 0].tick_params(axis='x', rotation=45)
        axes[0, 0].grid(axis='y', alpha=0.3)
        
        # 2. RMSE比较
        test_rmse_scores = [self.evaluation_results[name]['test_rmse'] for name in model_names]
        
        axes[0, 1].bar(model_names, test_rmse_scores, color='lightcoral', alpha=0.7)
        axes[0, 1].set_title('测试集RMSE比较')
        axes[0, 1].set_ylabel('RMSE')
        axes[0, 1].tick_params(axis='x', rotation=45)
        axes[0, 1].grid(axis='y', alpha=0.3)
        
        # 3. 交叉验证分数
        cv_means = [self.evaluation_results[name]['cv_mean'] for name in model_names]
        cv_stds = [self.evaluation_results[name]['cv_std'] for name in model_names]
        
        axes[0, 2].bar(model_names, cv_means, yerr=cv_stds, capsize=5, 
                       color='lightgreen', alpha=0.7)
        axes[0, 2].set_title('交叉验证分数')
        axes[0, 2].set_ylabel('CV R²分数')
        axes[0, 2].tick_params(axis='x', rotation=45)
        axes[0, 2].grid(axis='y', alpha=0.3)
        
        # 4. 最佳模型的预测 vs 实际值（训练集）
        best_model_name = max(model_names, key=lambda x: self.evaluation_results[x]['test_r2'])
        best_results = self.evaluation_results[best_model_name]
        
        axes[1, 0].scatter(best_results['y_train_true'], best_results['y_train_pred'], 
                          alpha=0.6, color='blue')
        axes[1, 0].plot([best_results['y_train_true'].min(), best_results['y_train_true'].max()],
                       [best_results['y_train_true'].min(), best_results['y_train_true'].max()],
                       'r--', lw=2)
        axes[1, 0].set_xlabel('实际收益率 (%)')
        axes[1, 0].set_ylabel('预测收益率 (%)')
        axes[1, 0].set_title(f'{self.model_configs[best_model_name]["name"]} - 训练集预测')
        axes[1, 0].grid(alpha=0.3)
        
        # 5. 最佳模型的预测 vs 实际值（测试集）
        axes[1, 1].scatter(best_results['y_test_true'], best_results['y_test_pred'], 
                          alpha=0.6, color='red')
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
            
            # 选择top 10特征
            top_indices = np.argsort(importances)[-10:]
            top_importances = importances[top_indices]
            top_features = [feature_names[i] for i in top_indices]
            
            axes[1, 2].barh(range(len(top_features)), top_importances, color='orange', alpha=0.7)
            axes[1, 2].set_yticks(range(len(top_features)))
            axes[1, 2].set_yticklabels(top_features)
            axes[1, 2].set_xlabel('特征重要性')
            axes[1, 2].set_title('Top 10 重要特征')
            axes[1, 2].grid(axis='x', alpha=0.3)
        else:
            axes[1, 2].text(0.5, 0.5, '该模型不支持\n特征重要性分析', 
                           ha='center', va='center', transform=axes[1, 2].transAxes)
            axes[1, 2].set_title('特征重要性')
        
        plt.tight_layout()
        plt.savefig('model_evaluation_results.png', dpi=300, bbox_inches='tight')
        print("📊 图表已保存为 'model_evaluation_results.png'")
        plt.show()
    
    def generate_detailed_report(self):
        """生成详细的评估报告"""
        print("\n📋 生成详细评估报告...")
        
        report = []
        report.append("=" * 100)
        report.append("🤖 股票收益预测机器学习模型 - 完整评估报告")
        report.append("=" * 100)
        report.append(f"⏰ 报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # 数据集信息
        report.append("📊 数据集信息")
        report.append("-" * 50)
        if hasattr(self, 'dataset_info'):
            for key, value in self.dataset_info.items():
                report.append(f"  {key}: {value}")
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
        
        # 使用建议
        report.append("💡 使用建议")
        report.append("-" * 50)
        if best_r2 >= 0.3:
            report.append("✅ 模型表现优秀，可用于实际投资决策参考")
        elif best_r2 >= 0.15:
            report.append("⚠️ 模型表现中等，建议结合其他分析方法使用")
        else:
            report.append("❌ 模型表现较差，需要进一步优化或收集更多数据")
        
        report.append("📋 改进建议：")
        report.append("  1. 增加更多的技术指标特征")
        report.append("  2. 考虑宏观经济指标")
        report.append("  3. 使用更长的历史数据")
        report.append("  4. 尝试深度学习模型")
        report.append("")
        
        report.append("=" * 100)
        
        # 保存报告
        report_text = "\n".join(report)
        with open('model_evaluation_report.txt', 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print(report_text)
        print("\n📄 详细报告已保存为 'model_evaluation_report.txt'")
        
        return report_text
    
    def run_complete_pipeline(self):
        """运行完整的机器学习管道"""
        print("🚀 启动完整机器学习管道")
        print("基于增强版财务因子的股票收益预测模型")
        print("=" * 100)
        
        try:
            # 1. 数据准备
            dataset = self.prepare_comprehensive_dataset()
            if dataset is None:
                print("❌ 数据准备失败，终止程序")
                return False
            
            # 保存数据集信息
            self.dataset_info = {
                '总样本数': len(dataset),
                '股票数量': dataset['ts_code'].nunique(),
                '时间范围': f"{dataset['end_date'].min()} 至 {dataset['end_date'].max()}",
                '特征数量': len([col for col in dataset.columns if col not in ['ts_code', 'end_date', 'future_20d_return']])
            }
            
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
            
            return True
            
        except Exception as e:
            print(f"❌ 管道执行失败：{e}")
            return False
        
        finally:
            # 关闭数据库连接
            if hasattr(self, 'factor_calculator'):
                self.factor_calculator.close()

def main():
    """主函数"""
    print("🤖 启动股票收益预测机器学习系统")
    print("基于增强版财务因子的完整模型训练与评估")
    print("=" * 100)
    
    # 创建并运行完整模型
    ml_model = CompleteMLModel()
    success = ml_model.run_complete_pipeline()
    
    if success:
        print("\n✅ 系统运行成功！")
        print("📁 生成的文件：")
        print("  - model_evaluation_results.png: 可视化图表")
        print("  - model_evaluation_report.txt: 详细评估报告")
        print("\n💡 您现在可以查看模型的完整测评结果！")
    else:
        print("\n❌ 系统运行失败，请检查错误信息")

if __name__ == "__main__":
    main() 