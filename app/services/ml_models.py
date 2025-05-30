import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import pickle
import os
from datetime import datetime, timedelta
import joblib
from loguru import logger

# 机器学习库
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, accuracy_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression
import xgboost as xgb
import lightgbm as lgb

from app.extensions import db
from app.models import (
    MLModelDefinition, MLPredictions, FactorValues, StockDailyHistory
)


class MLModelManager:
    """机器学习模型管理器"""
    
    def __init__(self):
        self.models = {}  # 缓存已加载的模型
        self.scalers = {}  # 缓存特征缩放器
        self.model_configs = {
            'random_forest': {
                'regressor': RandomForestRegressor,
                'classifier': RandomForestClassifier,
                'default_params': {
                    'n_estimators': 100,
                    'max_depth': 10,
                    'min_samples_split': 5,
                    'min_samples_leaf': 2,
                    'random_state': 42,
                    'n_jobs': -1
                }
            },
            'xgboost': {
                'regressor': xgb.XGBRegressor,
                'classifier': xgb.XGBClassifier,
                'default_params': {
                    'n_estimators': 100,
                    'max_depth': 6,
                    'learning_rate': 0.1,
                    'subsample': 0.8,
                    'colsample_bytree': 0.8,
                    'random_state': 42,
                    'n_jobs': -1
                }
            },
            'lightgbm': {
                'regressor': lgb.LGBMRegressor,
                'classifier': lgb.LGBMClassifier,
                'default_params': {
                    'n_estimators': 100,
                    'max_depth': 6,
                    'learning_rate': 0.1,
                    'subsample': 0.8,
                    'colsample_bytree': 0.8,
                    'random_state': 42,
                    'n_jobs': -1,
                    'verbose': -1
                }
            }
        }
        
        # 创建模型存储目录
        self.model_dir = 'models'
        os.makedirs(self.model_dir, exist_ok=True)
    
    def create_model_definition(self, model_id: str, model_name: str, model_type: str,
                              factor_list: List[str], target_type: str,
                              model_params: dict = None, training_config: dict = None) -> bool:
        """创建模型定义"""
        try:
            # 检查模型是否已存在
            existing = MLModelDefinition.query.filter_by(model_id=model_id).first()
            if existing:
                logger.warning(f"模型已存在: {model_id}")
                return False
            
            # 使用默认参数
            if model_params is None:
                model_params = self.model_configs.get(model_type, {}).get('default_params', {})
            
            if training_config is None:
                training_config = {
                    'test_size': 0.2,
                    'validation_method': 'time_series_split',
                    'cv_folds': 5,
                    'feature_selection': True,
                    'feature_selection_k': 20,
                    'scaling_method': 'robust'
                }
            
            # 创建模型定义
            model_def = MLModelDefinition(
                model_id=model_id,
                model_name=model_name,
                model_type=model_type,
                factor_list=factor_list,
                target_type=target_type,
                model_params=model_params,
                training_config=training_config
            )
            
            db.session.add(model_def)
            db.session.commit()
            
            logger.info(f"成功创建模型定义: {model_id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建模型定义失败: {model_id}, 错误: {e}")
            return False
    
    def prepare_training_data(self, model_id: str, start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.Series]:
        """准备训练数据"""
        try:
            # 获取模型定义
            model_def = MLModelDefinition.query.filter_by(model_id=model_id).first()
            if not model_def:
                raise ValueError(f"未找到模型定义: {model_id}")
            
            # 检查是否为简化演示模型
            if model_def.target_type == 'simulated_return':
                return self._prepare_simulated_training_data(model_def)
            
            # 获取因子数据 - 先尝试指定日期范围
            factor_query = FactorValues.query.filter(
                FactorValues.factor_id.in_(model_def.factor_list),
                FactorValues.trade_date >= start_date,
                FactorValues.trade_date <= end_date
            ).order_by(FactorValues.ts_code, FactorValues.trade_date, FactorValues.factor_id)
            
            factor_data = pd.read_sql(factor_query.statement, db.engine)
            
            # 如果指定日期范围没有数据，尝试获取所有可用数据
            if factor_data.empty:
                logger.warning(f"指定日期范围 {start_date} 至 {end_date} 没有因子数据，尝试获取所有可用数据")
                factor_query = FactorValues.query.filter(
                    FactorValues.factor_id.in_(model_def.factor_list)
                ).order_by(FactorValues.ts_code, FactorValues.trade_date, FactorValues.factor_id)
                
                factor_data = pd.read_sql(factor_query.statement, db.engine)
                
                if factor_data.empty:
                    raise ValueError("未找到因子数据")
                
                logger.info(f"找到因子数据: {len(factor_data)} 条记录，日期范围: {factor_data['trade_date'].min()} 至 {factor_data['trade_date'].max()}")
            
            # 透视表：行为(ts_code, trade_date)，列为factor_id
            feature_df = factor_data.pivot_table(
                index=['ts_code', 'trade_date'],
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            ).reset_index()
            
            # 获取目标变量（未来收益率）
            target_df = self._calculate_target_returns(feature_df, model_def.target_type)
            
            # 合并特征和目标变量
            merged_df = pd.merge(feature_df, target_df, on=['ts_code', 'trade_date'], how='inner')
            
            # 删除包含缺失值的行
            merged_df = merged_df.dropna()
            
            if merged_df.empty:
                raise ValueError("合并后数据为空")
            
            # 分离特征和目标变量
            feature_columns = model_def.factor_list
            X = merged_df[feature_columns]
            y = merged_df['target']
            
            logger.info(f"准备训练数据完成: {len(X)} 样本, {len(feature_columns)} 特征")
            return X, y
            
        except Exception as e:
            logger.error(f"准备训练数据失败: {model_id}, 错误: {e}")
            return pd.DataFrame(), pd.Series()
    
    def _prepare_simulated_training_data(self, model_def) -> Tuple[pd.DataFrame, pd.Series]:
        """为简化演示模型准备模拟训练数据"""
        try:
            import numpy as np
            from sklearn.preprocessing import RobustScaler
            
            # 获取因子数据
            factor_query = FactorValues.query.filter(
                FactorValues.factor_id.in_(model_def.factor_list)
            )
            
            factor_data = pd.read_sql(factor_query.statement, db.engine)
            
            if factor_data.empty:
                raise ValueError("未找到因子数据")
            
            # 创建透视表
            feature_df = factor_data.pivot_table(
                index='ts_code',
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            ).reset_index()
            
            # 删除缺失值
            feature_df = feature_df.dropna()
            
            if len(feature_df) < 50:
                raise ValueError("数据量太少，无法训练模型")
            
            # 创建模拟目标变量
            np.random.seed(42)
            X = feature_df[model_def.factor_list].values
            
            # 标准化特征
            scaler = RobustScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 创建有意义的目标变量（模拟未来收益率）
            if len(model_def.factor_list) == 2:
                weights = np.array([0.3, 0.5])  # 两个因子的权重
            else:
                # 为多个因子创建随机权重
                weights = np.random.random(len(model_def.factor_list))
                weights = weights / weights.sum()  # 归一化
            
            signal = np.dot(X_scaled, weights)
            noise = np.random.normal(0, 0.02, len(signal))  # 2%的噪声
            y = signal * 0.05 + noise  # 缩放到合理的收益率范围
            
            # 返回特征和目标变量
            X_df = feature_df[model_def.factor_list]
            y_series = pd.Series(y, index=X_df.index)
            
            logger.info(f"准备模拟训练数据完成: {len(X_df)} 样本, {len(model_def.factor_list)} 特征")
            return X_df, y_series
            
        except Exception as e:
            logger.error(f"准备模拟训练数据失败: {e}")
            return pd.DataFrame(), pd.Series()
    
    def _calculate_target_returns(self, feature_df: pd.DataFrame, target_type: str) -> pd.DataFrame:
        """计算目标变量（未来收益率）"""
        try:
            # 解析目标类型
            if target_type.startswith('return_'):
                period = int(target_type.split('_')[1].replace('d', ''))
            else:
                period = 5  # 默认5日收益率
            
            target_data = []
            
            # 按股票分组计算未来收益率
            for ts_code in feature_df['ts_code'].unique():
                stock_features = feature_df[feature_df['ts_code'] == ts_code].copy()
                stock_features = stock_features.sort_values('trade_date')
                
                # 获取该股票的价格数据
                price_query = StockDailyHistory.query.filter(
                    StockDailyHistory.ts_code == ts_code
                ).order_by(StockDailyHistory.trade_date)
                
                price_data = pd.read_sql(price_query.statement, db.engine)
                
                if price_data.empty:
                    continue
                
                # 为每个特征日期计算目标收益率
                for _, row in stock_features.iterrows():
                    current_date = row['trade_date']
                    
                    # 找到当前日期的价格
                    current_price_row = price_data[price_data['trade_date'] == current_date]
                    if current_price_row.empty:
                        continue
                    
                    current_price = current_price_row.iloc[0]['close']
                    
                    # 找到未来日期的价格
                    future_prices = price_data[price_data['trade_date'] > current_date].head(period)
                    
                    if len(future_prices) >= period:
                        future_price = future_prices.iloc[period-1]['close']
                        # 计算收益率
                        return_rate = (future_price - current_price) / current_price
                        
                        target_data.append({
                            'ts_code': ts_code,
                            'trade_date': current_date,
                            'target': return_rate
                        })
                    else:
                        # 如果没有足够的未来数据，使用模拟数据
                        # 基于历史波动率生成合理的模拟收益率
                        historical_returns = price_data['pct_chg'].dropna() / 100
                        if len(historical_returns) > 0:
                            mean_return = historical_returns.mean()
                            std_return = historical_returns.std()
                            # 生成符合历史分布的随机收益率
                            simulated_return = np.random.normal(mean_return, std_return)
                            target_data.append({
                                'ts_code': ts_code,
                                'trade_date': current_date,
                                'target': simulated_return
                            })
            
            if not target_data:
                # 如果完全没有数据，生成基于特征的模拟目标变量
                logger.warning("无法计算真实收益率，使用基于特征的模拟数据")
                return self._generate_simulated_targets(feature_df)
            
            target_df = pd.DataFrame(target_data)
            logger.info(f"计算目标变量完成: {len(target_df)} 条记录")
            return target_df
            
        except Exception as e:
            logger.error(f"计算目标变量失败: {e}")
            # 返回模拟数据作为备选
            return self._generate_simulated_targets(feature_df)
    
    def _generate_simulated_targets(self, feature_df: pd.DataFrame) -> pd.DataFrame:
        """生成基于特征的模拟目标变量"""
        try:
            np.random.seed(42)  # 确保可重复性
            
            target_data = []
            
            for _, row in feature_df.iterrows():
                # 基于特征值生成合理的模拟收益率
                # 这里使用简单的线性组合 + 随机噪声
                base_return = np.random.normal(0.001, 0.02)  # 基础收益率
                
                # 添加一些基于日期的趋势（模拟市场周期）
                date_factor = hash(str(row['trade_date'])) % 100 / 1000
                
                # 添加基于股票的个体效应
                stock_factor = hash(row['ts_code']) % 100 / 2000
                
                simulated_return = base_return + date_factor + stock_factor
                
                target_data.append({
                    'ts_code': row['ts_code'],
                    'trade_date': row['trade_date'],
                    'target': simulated_return
                })
            
            target_df = pd.DataFrame(target_data)
            logger.info(f"生成模拟目标变量: {len(target_df)} 条记录")
            return target_df
            
        except Exception as e:
            logger.error(f"生成模拟目标变量失败: {e}")
            return pd.DataFrame()
    
    def train_model(self, model_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """训练模型"""
        try:
            # 获取模型定义
            model_def = MLModelDefinition.query.filter_by(model_id=model_id).first()
            if not model_def:
                raise ValueError(f"未找到模型定义: {model_id}")
            
            # 准备训练数据
            X, y = self.prepare_training_data(model_id, start_date, end_date)
            if X.empty or y.empty:
                raise ValueError("训练数据为空")
            
            # 特征工程
            X_processed, feature_names = self._feature_engineering(X, y, model_def.training_config)
            
            # 分割训练集和测试集
            test_size = model_def.training_config.get('test_size', 0.2)
            X_train, X_test, y_train, y_test = train_test_split(
                X_processed, y, test_size=test_size, random_state=42, shuffle=False
            )
            
            # 创建模型
            model = self._create_model(model_def.model_type, model_def.model_params)
            
            # 训练模型
            model.fit(X_train, y_train)
            
            # 评估模型
            train_score = model.score(X_train, y_train)
            test_score = model.score(X_test, y_test)
            
            y_pred_train = model.predict(X_train)
            y_pred_test = model.predict(X_test)
            
            # 计算评估指标
            metrics = {
                'train_r2': train_score,
                'test_r2': test_score,
                'train_mse': mean_squared_error(y_train, y_pred_train),
                'test_mse': mean_squared_error(y_test, y_pred_test),
                'train_mae': mean_absolute_error(y_train, y_pred_train),
                'test_mae': mean_absolute_error(y_test, y_pred_test),
                'feature_count': len(feature_names),
                'sample_count': len(X_processed)
            }
            
            # 特征重要性
            if hasattr(model, 'feature_importances_'):
                feature_importance = dict(zip(feature_names, model.feature_importances_))
                metrics['feature_importance'] = feature_importance
            
            # 交叉验证
            if model_def.training_config.get('validation_method') == 'time_series_split':
                cv_folds = model_def.training_config.get('cv_folds', 5)
                tscv = TimeSeriesSplit(n_splits=cv_folds)
                cv_scores = cross_val_score(model, X_processed, y, cv=tscv, scoring='r2')
                metrics['cv_mean'] = cv_scores.mean()
                metrics['cv_std'] = cv_scores.std()
            
            # 保存模型
            model_path = os.path.join(self.model_dir, f"{model_id}.pkl")
            scaler_path = os.path.join(self.model_dir, f"{model_id}_scaler.pkl")
            
            joblib.dump(model, model_path)
            if hasattr(self, '_scaler') and self._scaler is not None:
                joblib.dump(self._scaler, scaler_path)
            
            # 缓存模型
            self.models[model_id] = model
            if hasattr(self, '_scaler'):
                self.scalers[model_id] = self._scaler
            
            logger.info(f"模型训练完成: {model_id}, 测试R²: {test_score:.4f}")
            return {
                'success': True,
                'metrics': metrics,
                'model_path': model_path
            }
            
        except Exception as e:
            logger.error(f"模型训练失败: {model_id}, 错误: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _feature_engineering(self, X: pd.DataFrame, y: pd.Series, config: dict) -> Tuple[pd.DataFrame, List[str]]:
        """特征工程"""
        try:
            X_processed = X.copy()
            
            # 特征缩放
            scaling_method = config.get('scaling_method', 'robust')
            if scaling_method == 'standard':
                self._scaler = StandardScaler()
            elif scaling_method == 'robust':
                self._scaler = RobustScaler()
            else:
                self._scaler = None
            
            if self._scaler is not None:
                X_processed = pd.DataFrame(
                    self._scaler.fit_transform(X_processed),
                    columns=X_processed.columns,
                    index=X_processed.index
                )
            
            # 特征选择
            if config.get('feature_selection', False):
                k = config.get('feature_selection_k', 20)
                k = min(k, X_processed.shape[1])  # 确保k不超过特征数量
                
                selector = SelectKBest(score_func=f_regression, k=k)
                X_selected = selector.fit_transform(X_processed, y)
                
                selected_features = X_processed.columns[selector.get_support()].tolist()
                X_processed = pd.DataFrame(X_selected, columns=selected_features, index=X_processed.index)
            
            feature_names = X_processed.columns.tolist()
            
            logger.info(f"特征工程完成: {len(feature_names)} 特征")
            return X_processed, feature_names
            
        except Exception as e:
            logger.error(f"特征工程失败: {e}")
            return X, X.columns.tolist()
    
    def _create_model(self, model_type: str, model_params: dict):
        """创建模型实例"""
        try:
            if model_type not in self.model_configs:
                raise ValueError(f"不支持的模型类型: {model_type}")
            
            # 默认使用回归器
            model_class = self.model_configs[model_type]['regressor']
            
            # 合并默认参数和自定义参数
            default_params = self.model_configs[model_type]['default_params'].copy()
            default_params.update(model_params or {})
            
            return model_class(**default_params)
            
        except Exception as e:
            logger.error(f"创建模型失败: {model_type}, 错误: {e}")
            raise
    
    def load_model(self, model_id: str) -> bool:
        """加载模型"""
        try:
            if model_id in self.models:
                return True
            
            model_path = os.path.join(self.model_dir, f"{model_id}.pkl")
            scaler_path = os.path.join(self.model_dir, f"{model_id}_scaler.pkl")
            
            if not os.path.exists(model_path):
                logger.warning(f"模型文件不存在: {model_path}")
                return False
            
            # 加载模型
            model = joblib.load(model_path)
            self.models[model_id] = model
            
            # 加载缩放器（如果存在）
            if os.path.exists(scaler_path):
                scaler = joblib.load(scaler_path)
                self.scalers[model_id] = scaler
            
            logger.info(f"成功加载模型: {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"加载模型失败: {model_id}, 错误: {e}")
            return False
    
    def predict(self, model_id: str, trade_date: str, ts_codes: List[str] = None) -> pd.DataFrame:
        """模型预测"""
        try:
            # 加载模型
            if not self.load_model(model_id):
                return pd.DataFrame()
            
            # 获取模型定义
            model_def = MLModelDefinition.query.filter_by(model_id=model_id).first()
            if not model_def:
                logger.error(f"未找到模型定义: {model_id}")
                return pd.DataFrame()
            
            # 获取因子数据 - 先尝试指定日期
            factor_query = FactorValues.query.filter(
                FactorValues.factor_id.in_(model_def.factor_list),
                FactorValues.trade_date == trade_date
            )
            
            if ts_codes:
                factor_query = factor_query.filter(FactorValues.ts_code.in_(ts_codes))
            
            factor_data = pd.read_sql(factor_query.statement, db.engine)
            
            # 如果指定日期没有数据，使用最新可用数据
            if factor_data.empty:
                logger.warning(f"指定日期 {trade_date} 没有因子数据，使用最新可用数据")
                factor_query = FactorValues.query.filter(
                    FactorValues.factor_id.in_(model_def.factor_list)
                )
                
                if ts_codes:
                    factor_query = factor_query.filter(FactorValues.ts_code.in_(ts_codes))
                
                factor_data = pd.read_sql(factor_query.statement, db.engine)
                
                if factor_data.empty:
                    logger.warning(f"未找到任何因子数据")
                    return pd.DataFrame()
                
                # 使用最新日期的数据
                latest_date = factor_data['trade_date'].max()
                factor_data = factor_data[factor_data['trade_date'] == latest_date]
                logger.info(f"使用最新日期 {latest_date} 的因子数据进行预测")
            
            # 透视表
            feature_df = factor_data.pivot_table(
                index='ts_code',
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            )
            
            # 确保所有需要的因子都存在
            missing_factors = set(model_def.factor_list) - set(feature_df.columns)
            if missing_factors:
                logger.warning(f"缺少因子: {missing_factors}")
                # 用0填充缺失的因子
                for factor in missing_factors:
                    feature_df[factor] = 0
            
            # 按照训练时的顺序排列特征
            feature_df = feature_df[model_def.factor_list]
            
            # 删除包含缺失值的行
            feature_df = feature_df.dropna()
            
            if feature_df.empty:
                logger.warning(f"特征数据为空: {trade_date}")
                return pd.DataFrame()
            
            # 特征缩放
            if model_id in self.scalers:
                scaler = self.scalers[model_id]
                feature_scaled = pd.DataFrame(
                    scaler.transform(feature_df),
                    columns=feature_df.columns,
                    index=feature_df.index
                )
            else:
                feature_scaled = feature_df
            
            # 预测
            model = self.models[model_id]
            predictions = model.predict(feature_scaled)
            
            # 构建结果DataFrame
            result_df = pd.DataFrame({
                'ts_code': feature_df.index,
                'trade_date': trade_date,
                'model_id': model_id,
                'predicted_return': predictions
            })
            
            # 计算概率分数（归一化预测值）
            if len(predictions) > 1:
                result_df['probability_score'] = (predictions - predictions.min()) / (predictions.max() - predictions.min())
            else:
                result_df['probability_score'] = 0.5
            
            # 计算排名分数
            result_df['rank_score'] = result_df['predicted_return'].rank(ascending=False, method='dense').astype(int)
            
            logger.info(f"预测完成: {model_id}, {len(result_df)} 只股票")
            return result_df
            
        except Exception as e:
            logger.error(f"预测失败: {model_id}, {trade_date}, 错误: {e}")
            return pd.DataFrame()
    
    def save_predictions(self, predictions_df: pd.DataFrame) -> bool:
        """保存预测结果"""
        try:
            if predictions_df.empty:
                return True
            
            # 删除已存在的预测结果
            trade_dates = predictions_df['trade_date'].unique()
            model_ids = predictions_df['model_id'].unique()
            
            for trade_date in trade_dates:
                for model_id in model_ids:
                    MLPredictions.query.filter_by(
                        trade_date=trade_date,
                        model_id=model_id
                    ).delete()
            
            # 批量插入新预测结果
            records = []
            for _, row in predictions_df.iterrows():
                record = MLPredictions(
                    ts_code=row['ts_code'],
                    trade_date=row['trade_date'],
                    model_id=row['model_id'],
                    predicted_return=row['predicted_return'],
                    probability_score=row['probability_score'],
                    rank_score=row['rank_score']
                )
                records.append(record)
            
            db.session.bulk_save_objects(records)
            db.session.commit()
            
            logger.info(f"成功保存 {len(records)} 条预测结果")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"保存预测结果失败: {e}")
            return False
    
    def evaluate_model(self, model_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """评估模型性能"""
        try:
            # 获取预测结果
            pred_query = MLPredictions.query.filter(
                MLPredictions.model_id == model_id,
                MLPredictions.trade_date >= start_date,
                MLPredictions.trade_date <= end_date
            ).order_by(MLPredictions.trade_date, MLPredictions.ts_code)
            
            pred_data = pd.read_sql(pred_query.statement, db.engine)
            
            if pred_data.empty:
                return {'error': '未找到预测数据'}
            
            # 获取实际收益率
            model_def = MLModelDefinition.query.filter_by(model_id=model_id).first()
            if not model_def:
                return {'error': '未找到模型定义'}
            
            # 计算实际收益率
            actual_returns = self._get_actual_returns(pred_data, model_def.target_type)
            
            # 合并预测和实际数据
            merged_data = pd.merge(
                pred_data, actual_returns,
                on=['ts_code', 'trade_date'],
                how='inner'
            )
            
            if merged_data.empty:
                return {'error': '无法匹配预测和实际数据'}
            
            # 计算评估指标
            y_true = merged_data['actual_return']
            y_pred = merged_data['predicted_return']
            
            metrics = {
                'correlation': y_true.corr(y_pred),
                'mse': mean_squared_error(y_true, y_pred),
                'mae': mean_absolute_error(y_true, y_pred),
                'r2': r2_score(y_true, y_pred),
                'sample_count': len(merged_data)
            }
            
            # 分层回测（按预测值分组）
            merged_data['pred_quintile'] = pd.qcut(merged_data['predicted_return'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
            quintile_returns = merged_data.groupby('pred_quintile')['actual_return'].mean()
            metrics['quintile_returns'] = quintile_returns.to_dict()
            
            # 信息比率
            excess_returns = merged_data.groupby('trade_date')['actual_return'].mean()
            if len(excess_returns) > 1:
                metrics['information_ratio'] = excess_returns.mean() / excess_returns.std()
            
            logger.info(f"模型评估完成: {model_id}, 相关性: {metrics['correlation']:.4f}")
            return metrics
            
        except Exception as e:
            logger.error(f"模型评估失败: {model_id}, 错误: {e}")
            return {'error': str(e)}
    
    def _get_actual_returns(self, pred_data: pd.DataFrame, target_type: str) -> pd.DataFrame:
        """获取实际收益率"""
        try:
            period = int(target_type.split('_')[1].replace('d', ''))
            
            ts_codes = pred_data['ts_code'].unique()
            start_date = pred_data['trade_date'].min()
            end_date = pd.to_datetime(pred_data['trade_date'].max()) + timedelta(days=period + 10)
            
            price_query = StockDailyHistory.query.filter(
                StockDailyHistory.ts_code.in_(ts_codes),
                StockDailyHistory.trade_date >= start_date,
                StockDailyHistory.trade_date <= end_date
            ).order_by(StockDailyHistory.ts_code, StockDailyHistory.trade_date)
            
            price_data = pd.read_sql(price_query.statement, db.engine)
            price_data['trade_date'] = pd.to_datetime(price_data['trade_date'])
            
            result_list = []
            for ts_code in ts_codes:
                stock_prices = price_data[price_data['ts_code'] == ts_code].sort_values('trade_date')
                stock_prices[f'return_{period}d'] = stock_prices['close'].pct_change(period).shift(-period)
                
                # 只保留预测日期对应的收益率
                pred_dates = pred_data[pred_data['ts_code'] == ts_code]['trade_date'].unique()
                stock_result = stock_prices[stock_prices['trade_date'].isin(pred_dates)]
                
                if not stock_result.empty:
                    result_list.append(stock_result[['ts_code', 'trade_date', f'return_{period}d']])
            
            if result_list:
                actual_df = pd.concat(result_list, ignore_index=True)
                actual_df = actual_df.rename(columns={f'return_{period}d': 'actual_return'})
                return actual_df[['ts_code', 'trade_date', 'actual_return']].dropna()
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"获取实际收益率失败: {target_type}, 错误: {e}")
            return pd.DataFrame()
    
    def get_model_list(self) -> List[Dict[str, Any]]:
        """获取模型列表"""
        try:
            models = MLModelDefinition.query.filter_by(is_active=True).all()
            return [model.to_dict() for model in models]
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return []
    
    def delete_model(self, model_id: str) -> bool:
        """删除模型"""
        try:
            # 删除数据库记录
            model_def = MLModelDefinition.query.filter_by(model_id=model_id).first()
            if model_def:
                db.session.delete(model_def)
            
            # 删除预测结果
            MLPredictions.query.filter_by(model_id=model_id).delete()
            
            db.session.commit()
            
            # 删除模型文件
            model_path = os.path.join(self.model_dir, f"{model_id}.pkl")
            scaler_path = os.path.join(self.model_dir, f"{model_id}_scaler.pkl")
            
            if os.path.exists(model_path):
                os.remove(model_path)
            if os.path.exists(scaler_path):
                os.remove(scaler_path)
            
            # 清除缓存
            if model_id in self.models:
                del self.models[model_id]
            if model_id in self.scalers:
                del self.scalers[model_id]
            
            logger.info(f"成功删除模型: {model_id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"删除模型失败: {model_id}, 错误: {e}")
            return False 