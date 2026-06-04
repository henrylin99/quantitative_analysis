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

from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import (
    FactorRepository,
    ModelRepository,
    ParquetStateStore,
)


class MLModelManager:
    """机器学习模型管理器"""
    SUPPORTED_TARGET_TYPES = {"return_1d", "return_5d", "return_20d", "ranking"}
    
    def __init__(self, state_store: ParquetStateStore = None):
        self.models = {}  # 缓存已加载的模型
        self.scalers = {}  # 缓存特征缩放器
        self.state_store = state_store or ParquetStateStore()
        self.factor_repo = FactorRepository(self.state_store)
        self.model_repo = ModelRepository(self.state_store)
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

    @classmethod
    def is_supported_target_type(cls, target_type: str) -> bool:
        return target_type in cls.SUPPORTED_TARGET_TYPES

    @staticmethod
    def _target_period(target_type: str) -> int:
        if isinstance(target_type, str) and target_type.startswith("return_"):
            return int(target_type.split("_")[1].replace("d", ""))
        return 5

    def _get_model_definition(self, model_id: str) -> Dict[str, Any]:
        model_def = self.model_repo.get_definition(model_id)
        if not model_def:
            return {}
        model_def = dict(model_def)
        model_def["factor_list"] = model_def.get("factor_list") or []
        model_def["model_params"] = model_def.get("model_params") or {}
        model_def["training_config"] = model_def.get("training_config") or {}
        return model_def

    def resolve_training_date_range(self, model_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Return a training date range that can calculate future-return labels."""
        model_def = self._get_model_definition(model_id)
        if not model_def:
            raise ValueError(f"未找到模型定义: {model_id}")

        start_dt = pd.to_datetime(start_date, errors="coerce")
        end_dt = pd.to_datetime(end_date, errors="coerce")
        if pd.isna(start_dt) or pd.isna(end_dt):
            raise ValueError("训练日期格式无效")
        start_dt = start_dt.normalize()
        end_dt = end_dt.normalize()
        if start_dt > end_dt:
            raise ValueError("开始日期不能晚于结束日期")

        period = self._target_period(model_def["target_type"])
        calendar_dates = pd.to_datetime(ParquetDataReader().get_trade_dates(), errors="coerce")
        calendar_dates = sorted(dt.normalize() for dt in calendar_dates.dropna().drop_duplicates())
        if not calendar_dates:
            raise ValueError("未找到日线交易日数据，无法建议训练日期")
        calendar_index = {dt: index for index, dt in enumerate(calendar_dates)}

        def valid_trainable_dates(frame: pd.DataFrame, restrict_to_request: bool) -> List[pd.Timestamp]:
            dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna().dt.normalize().drop_duplicates()
            if restrict_to_request:
                dates = [dt for dt in dates if start_dt <= dt <= end_dt]
            return sorted(
                dt
                for dt in dates
                if dt in calendar_index and calendar_index[dt] + period < len(calendar_dates)
            )

        requested_factor_data = self.factor_repo.get_values(
            factor_ids=model_def["factor_list"],
            start_date=start_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
        )
        valid_dates = []
        using_fallback_dates = True
        if not requested_factor_data.empty and "trade_date" in requested_factor_data.columns:
            valid_dates = valid_trainable_dates(requested_factor_data, restrict_to_request=True)
            using_fallback_dates = not valid_dates

        if not valid_dates:
            factor_data = self.factor_repo.get_values(factor_ids=model_def["factor_list"])
            if factor_data.empty or "trade_date" not in factor_data.columns:
                raise ValueError("未找到因子数据，无法建议训练日期")
            valid_dates = valid_trainable_dates(factor_data, restrict_to_request=False)
        if not valid_dates:
            raise ValueError(f"没有可计算 {model_def['target_type']} 的训练日期")

        if using_fallback_dates:
            resolved_end = max(valid_dates)
            resolved_start = resolved_end
        else:
            resolved_end = min(end_dt, max(valid_dates))
            resolved_start_candidates = [dt for dt in valid_dates if dt <= resolved_end]
            resolved_start = max(start_dt, min(resolved_start_candidates))
        requested_start = start_dt.strftime("%Y-%m-%d")
        requested_end = end_dt.strftime("%Y-%m-%d")
        resolved_start_text = resolved_start.strftime("%Y-%m-%d")
        resolved_end_text = resolved_end.strftime("%Y-%m-%d")
        adjusted = requested_start != resolved_start_text or requested_end != resolved_end_text
        message = None
        if adjusted:
            message = f"训练日期已自动调整为可计算未来收益的区间: {resolved_start_text} 至 {resolved_end_text}"

        return {
            "model_id": model_id,
            "target_type": model_def["target_type"],
            "target_period": period,
            "start_date": resolved_start_text,
            "end_date": resolved_end_text,
            "requested_start_date": requested_start,
            "requested_end_date": requested_end,
            "adjusted": adjusted,
            "message": message,
        }

    def suggest_training_date_range(self, model_id: str) -> Dict[str, Any]:
        """Suggest a short, recent training range that has future-return labels."""
        model_def = self._get_model_definition(model_id)
        if not model_def:
            raise ValueError(f"未找到模型定义: {model_id}")

        period = self._target_period(model_def["target_type"])
        factor_data = self.factor_repo.get_values(factor_ids=model_def["factor_list"])
        if factor_data.empty or "trade_date" not in factor_data.columns:
            raise ValueError("未找到因子数据，无法建议训练日期")

        factor_dates = pd.to_datetime(factor_data["trade_date"], errors="coerce").dropna().dt.normalize().drop_duplicates()
        factor_dates = sorted(factor_dates)
        if not factor_dates:
            raise ValueError("未找到有效因子日期，无法建议训练日期")

        calendar_dates = pd.to_datetime(ParquetDataReader().get_trade_dates(), errors="coerce")
        calendar_dates = sorted(dt.normalize() for dt in calendar_dates.dropna().drop_duplicates())
        if not calendar_dates:
            raise ValueError("未找到日线交易日数据，无法建议训练日期")

        calendar_index = {dt: index for index, dt in enumerate(calendar_dates)}
        valid_dates = [
            dt
            for dt in factor_dates
            if dt in calendar_index and calendar_index[dt] + period < len(calendar_dates)
        ]
        if not valid_dates:
            raise ValueError(f"没有可计算 {model_def['target_type']} 的训练日期")

        resolved_date = max(valid_dates).strftime("%Y-%m-%d")
        return {
            "model_id": model_id,
            "target_type": model_def["target_type"],
            "target_period": period,
            "start_date": resolved_date,
            "end_date": resolved_date,
            "adjusted": True,
            "message": f"已建议最近可计算未来收益的训练日期: {resolved_date}",
        }
    
    def create_model_definition(self, model_id: str, model_name: str, model_type: str,
                              factor_list: List[str], target_type: str,
                              model_params: dict = None, training_config: dict = None) -> bool:
        """创建模型定义"""
        try:
            if not self.is_supported_target_type(target_type):
                logger.warning(f"不支持的目标类型: {target_type}")
                return False

            if self.model_repo.get_definition(model_id):
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
            self.model_repo.upsert_definition(
                {
                    "model_id": model_id,
                    "model_name": model_name,
                    "model_type": model_type,
                    "factor_list": factor_list,
                    "target_type": target_type,
                    "model_params": model_params,
                    "training_config": training_config,
                    "is_active": True,
                }
            )
            
            logger.info(f"成功创建模型定义: {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"创建模型定义失败: {model_id}, 错误: {e}")
            return False
    
    def prepare_training_data(self, model_id: str, start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.Series]:
        """准备训练数据"""
        try:
            # 获取模型定义
            model_def = self._get_model_definition(model_id)
            if not model_def:
                raise ValueError(f"未找到模型定义: {model_id}")

            if not self.is_supported_target_type(model_def["target_type"]):
                raise ValueError(f"不支持的目标类型: {model_def['target_type']}")
            
            # 获取因子数据 - 先尝试指定日期范围
            factor_data = self.factor_repo.get_values(
                factor_ids=model_def["factor_list"],
                start_date=start_date,
                end_date=end_date,
            )
            
            # 如果指定日期范围没有数据，尝试获取所有可用数据
            if factor_data.empty:
                logger.warning(f"指定日期范围 {start_date} 至 {end_date} 没有因子数据，尝试获取所有可用数据")
                factor_data = self.factor_repo.get_values(factor_ids=model_def["factor_list"])
                
                if factor_data.empty:
                    raise ValueError("未找到因子数据")
                
                logger.info(f"找到因子数据: {len(factor_data)} 条记录，日期范围: {factor_data['trade_date'].min()} 至 {factor_data['trade_date'].max()}")

            factor_data = factor_data.copy()
            factor_data["trade_date"] = pd.to_datetime(factor_data["trade_date"], errors="coerce")
            factor_data = factor_data.dropna(subset=["trade_date"])
            
            # 透视表：行为(ts_code, trade_date)，列为factor_id
            feature_df = factor_data.pivot_table(
                index=['ts_code', 'trade_date'],
                columns='factor_id',
                values='factor_value',
                aggfunc='first'
            ).reset_index()
            
            # 获取目标变量（未来收益率）
            target_df = self._calculate_target_returns(feature_df, model_def["target_type"])
            if not target_df.empty:
                target_df = target_df.copy()
                target_df["trade_date"] = pd.to_datetime(target_df["trade_date"], errors="coerce")
                target_df = target_df.dropna(subset=["trade_date"])
            
            # 合并特征和目标变量
            merged_df = pd.merge(feature_df, target_df, on=['ts_code', 'trade_date'], how='inner')
            
            # 删除包含缺失值的行
            merged_df = merged_df.dropna()
            
            if merged_df.empty:
                raise ValueError("合并后数据为空")
            
            # 分离特征和目标变量
            feature_columns = model_def["factor_list"]
            X = merged_df[feature_columns]
            y = merged_df['target']
            
            logger.info(f"准备训练数据完成: {len(X)} 样本, {len(feature_columns)} 特征")
            return X, y
            
        except Exception as e:
            logger.error(f"准备训练数据失败: {model_id}, 错误: {e}")
            return pd.DataFrame(), pd.Series()
    
    def _calculate_target_returns(self, feature_df: pd.DataFrame, target_type: str) -> pd.DataFrame:
        """计算目标变量（未来收益率）"""
        try:
            empty_target = pd.DataFrame(columns=['ts_code', 'trade_date', 'target'])
            if feature_df.empty or not {'ts_code', 'trade_date'}.issubset(feature_df.columns):
                return empty_target

            # 解析目标类型
            period = self._target_period(target_type)

            feature_keys = feature_df[['ts_code', 'trade_date']].copy()
            feature_keys['ts_code'] = feature_keys['ts_code'].astype(str)
            feature_keys['trade_date'] = pd.to_datetime(feature_keys['trade_date'], errors='coerce')
            feature_keys = feature_keys.dropna(subset=['ts_code', 'trade_date'])
            feature_keys['trade_date'] = feature_keys['trade_date'].dt.normalize()
            feature_keys = feature_keys.drop_duplicates().reset_index(drop=True)
            if feature_keys.empty:
                return empty_target

            ts_codes = feature_keys['ts_code'].dropna().unique().tolist()
            min_date = feature_keys['trade_date'].min()
            max_date = feature_keys['trade_date'].max()
            price_end_date = max_date + timedelta(days=period + 10)

            reader = ParquetDataReader()
            price_data = reader.get_daily(
                ts_codes=ts_codes,
                start_date=min_date.strftime("%Y-%m-%d"),
                end_date=price_end_date.strftime("%Y-%m-%d"),
            )

            if price_data.empty:
                logger.warning("未找到任何日线价格数据，返回空目标数据")
                return empty_target

            price_data = price_data.copy()
            required_cols = {'ts_code', 'trade_date', 'close'}
            if not required_cols.issubset(price_data.columns):
                logger.warning(f"日线价格数据缺少必要列: {sorted(required_cols - set(price_data.columns))}")
                return empty_target

            price_data['ts_code'] = price_data['ts_code'].astype(str)
            price_data['trade_date'] = pd.to_datetime(price_data['trade_date'], errors='coerce')
            price_data['close'] = pd.to_numeric(price_data['close'], errors='coerce')
            price_data = price_data.dropna(subset=['ts_code', 'trade_date', 'close'])
            price_data = price_data[price_data['close'] != 0]
            price_data['trade_date'] = price_data['trade_date'].dt.normalize()
            price_data = price_data.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
            price_data['future_close'] = price_data.groupby('ts_code')['close'].shift(-period)
            price_data['target'] = (price_data['future_close'] - price_data['close']) / price_data['close']

            target_df = price_data[['ts_code', 'trade_date', 'target']].dropna(subset=['target'])
            target_df = pd.merge(feature_keys, target_df, on=['ts_code', 'trade_date'], how='inner')

            if target_df.empty:
                logger.warning("无法计算真实收益率，返回空目标数据")
                return empty_target
            
            logger.info(f"计算目标变量完成: {len(target_df)} 条记录")
            return target_df
            
        except Exception as e:
            logger.error(f"计算目标变量失败: {e}")
            return pd.DataFrame(columns=['ts_code', 'trade_date', 'target'])
    
    def train_model(self, model_id: str, start_date: str, end_date: str, progress_callback=None) -> Dict[str, Any]:
        """训练模型"""
        try:
            def report(progress: float, step: str, message: str = None):
                if callable(progress_callback):
                    progress_callback(progress, step, message)

            # 获取模型定义
            model_def = self._get_model_definition(model_id)
            if not model_def:
                raise ValueError(f"未找到模型定义: {model_id}")
            
            # 准备训练数据
            report(15.0, "准备训练数据", "正在准备训练数据...")
            X, y = self.prepare_training_data(model_id, start_date, end_date)
            if X.empty or y.empty:
                raise ValueError("训练数据为空")
            
            # 特征工程
            report(35.0, "特征工程", "正在执行特征工程...")
            X_processed, feature_names = self._feature_engineering(X, y, model_def["training_config"])
            
            # 分割训练集和测试集
            report(50.0, "拆分训练集", "正在拆分训练集和测试集...")
            test_size = model_def["training_config"].get('test_size', 0.2)
            X_train, X_test, y_train, y_test = train_test_split(
                X_processed, y, test_size=test_size, random_state=42, shuffle=False
            )
            
            # 创建模型
            report(65.0, "创建模型", f"正在创建模型: {model_def['model_type']}")
            model = self._create_model(model_def["model_type"], model_def["model_params"])
            
            # 训练模型
            report(80.0, "训练模型", "正在训练模型...")
            model.fit(X_train, y_train)
            
            # 评估模型
            report(90.0, "评估模型", "正在评估模型表现...")
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
            if model_def["training_config"].get('validation_method') == 'time_series_split':
                cv_folds = model_def["training_config"].get('cv_folds', 5)
                tscv = TimeSeriesSplit(n_splits=cv_folds)
                cv_scores = cross_val_score(model, X_processed, y, cv=tscv, scoring='r2')
                metrics['cv_mean'] = cv_scores.mean()
                metrics['cv_std'] = cv_scores.std()
            
            # 保存模型
            report(95.0, "保存模型", "正在保存模型和元数据...")
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
            report(100.0, "训练完成", "训练任务已完成")
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
            model_def = self._get_model_definition(model_id)
            if not model_def:
                logger.error(f"未找到模型定义: {model_id}")
                return pd.DataFrame()
            
            # 获取因子数据 - 先尝试指定日期
            factor_data = self.factor_repo.get_values(
                factor_ids=model_def["factor_list"],
                trade_date=trade_date,
                ts_codes=ts_codes,
            )
            
            # 如果指定日期没有数据，使用最新可用数据
            if factor_data.empty:
                logger.warning(f"指定日期 {trade_date} 没有因子数据，使用最新可用数据")
                factor_data = self.factor_repo.get_values(
                    factor_ids=model_def["factor_list"],
                    ts_codes=ts_codes,
                )
                
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
            missing_factors = set(model_def["factor_list"]) - set(feature_df.columns)
            if missing_factors:
                logger.warning(f"缺少因子: {missing_factors}")
                # 用0填充缺失的因子
                for factor in missing_factors:
                    feature_df[factor] = 0
            
            # 按照训练时的顺序排列特征
            feature_df = feature_df[model_def["factor_list"]]
            
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

            written = self.model_repo.save_predictions(predictions_df)
            logger.info(f"成功保存 {written} 条预测结果")
            return True
            
        except Exception as e:
            logger.error(f"保存预测结果失败: {e}")
            return False
    
    def evaluate_model(self, model_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """评估模型性能"""
        try:
            # 获取预测结果
            pred_data = self.model_repo.get_predictions(
                model_id=model_id,
                trade_date=None,
            )
            if not pred_data.empty:
                pred_data = pred_data[
                    (pred_data["trade_date"] >= start_date) &
                    (pred_data["trade_date"] <= end_date)
                ].sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
            
            if pred_data.empty:
                return {'error': '未找到预测数据'}
            
            # 获取实际收益率
            model_def = self._get_model_definition(model_id)
            if not model_def:
                return {'error': '未找到模型定义'}
            
            # 计算实际收益率
            actual_returns = self._get_actual_returns(pred_data, model_def["target_type"])
            
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
            
            price_data = ParquetDataReader().get_daily(
                ts_codes=list(ts_codes),
                start_date=str(start_date)[:10] if not isinstance(start_date, str) else start_date,
                end_date=end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date)[:10],
            )
            
            result_list = []
            for ts_code in ts_codes:
                stock_prices = price_data[price_data['ts_code'] == ts_code].sort_values('trade_date')
                stock_prices[f'return_{period}d'] = stock_prices['close'].pct_change(period).shift(-period)
                
                # 只保留预测日期对应的收益率
                pred_dates = pd.to_datetime(
                    pred_data[pred_data['ts_code'] == ts_code]['trade_date'].unique()
                )
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
            return self.model_repo.list_definitions(include_inactive=False)
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return []

    def get_model_detail(self, model_id: str) -> Dict[str, Any]:
        """获取模型详情"""
        try:
            model_def = self._get_model_definition(model_id)
            if not model_def:
                return {}

            predictions = self.model_repo.get_predictions(model_id=model_id)
            prediction_summary = {
                "total_predictions": 0,
                "unique_trade_dates": 0,
                "unique_ts_codes": 0,
                "latest_trade_date": None,
                "latest_created_at": None,
            }
            recent_predictions: List[Dict[str, Any]] = []
            if not predictions.empty:
                pred_df = predictions.copy()
                if "trade_date" in pred_df.columns:
                    pred_df["trade_date"] = pd.to_datetime(pred_df["trade_date"], errors="coerce")
                if "created_at" in pred_df.columns:
                    pred_df["created_at"] = pd.to_datetime(pred_df["created_at"], errors="coerce")
                sort_cols = [c for c in ["trade_date", "created_at", "ts_code"] if c in pred_df.columns]
                if sort_cols:
                    ascending = [False, False, True][: len(sort_cols)]
                    pred_df = pred_df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)

                prediction_summary["total_predictions"] = int(len(pred_df))
                if "trade_date" in pred_df.columns and pred_df["trade_date"].notna().any():
                    prediction_summary["unique_trade_dates"] = int(pred_df["trade_date"].dropna().dt.normalize().nunique())
                    latest_trade_date = pred_df["trade_date"].dropna().max()
                    prediction_summary["latest_trade_date"] = latest_trade_date.strftime("%Y-%m-%d")
                if "ts_code" in pred_df.columns:
                    prediction_summary["unique_ts_codes"] = int(pred_df["ts_code"].dropna().astype(str).nunique())
                if "created_at" in pred_df.columns and pred_df["created_at"].notna().any():
                    latest_created_at = pred_df["created_at"].dropna().max()
                    prediction_summary["latest_created_at"] = latest_created_at.isoformat()

                recent_predictions = pred_df.head(10).copy()
                for column in ["trade_date", "created_at"]:
                    if column in recent_predictions.columns:
                        recent_predictions[column] = recent_predictions[column].apply(
                            lambda value: value.isoformat() if hasattr(value, "isoformat") else value
                        )
                recent_predictions = recent_predictions.astype(object).where(pd.notna(recent_predictions), None).to_dict("records")

            model_path = os.path.join(self.model_dir, f"{model_id}.pkl")
            scaler_path = os.path.join(self.model_dir, f"{model_id}_scaler.pkl")

            return {
                **model_def,
                "model_file_exists": os.path.exists(model_path),
                "scaler_file_exists": os.path.exists(scaler_path),
                "prediction_summary": prediction_summary,
                "recent_predictions": recent_predictions,
            }
        except Exception as e:
            logger.error(f"获取模型详情失败: {model_id}, 错误: {e}")
            return {}

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        """删除模型"""
        try:
            model_def = self._get_model_definition(model_id)
            if not model_def:
                return {
                    'success': False,
                    'error': f'未找到模型定义: {model_id}'
                }

            pred_data = self.model_repo.get_predictions(model_id=model_id)
            deleted_prediction_count = len(pred_data) if not pred_data.empty else 0
            self.model_repo.delete_definition(model_id)
            if not pred_data.empty:
                deleted_prediction_count = len(pred_data)
            # delete_definition already removes predictions for the model
            
            model_path = os.path.join(self.model_dir, f"{model_id}.pkl")
            scaler_path = os.path.join(self.model_dir, f"{model_id}_scaler.pkl")
            deleted_files = []

            if os.path.exists(model_path):
                os.remove(model_path)
                deleted_files.append(model_path)
            if os.path.exists(scaler_path):
                os.remove(scaler_path)
                deleted_files.append(scaler_path)

            if model_id in self.models:
                del self.models[model_id]
            if model_id in self.scalers:
                del self.scalers[model_id]
            
            logger.info(f"成功删除模型: {model_id}")
            return {
                'success': True,
                'model_id': model_id,
                'deleted_prediction_count': int(deleted_prediction_count or 0),
                'deleted_files': deleted_files
            }
            
        except Exception as e:
            logger.error(f"删除模型失败: {model_id}, 错误: {e}")
            return {
                'success': False,
                'error': str(e)
            }
