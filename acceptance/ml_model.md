# 模块：ml_model

## 职责
XGBoost/LightGBM/RandomForest 模型生命周期管理，包含真实训练、预测、模型持久化。禁止静默降级为 mock 训练。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| ML 模型 API 合约 | tests/api/test_ml_model_contract.py | module_ml_model |
| 真实训练守卫 | tests/services/test_ml_models_real_training_guard.py | module_ml_model |
| 数据源合约 | tests/services/test_ml_models_source_contract.py | module_ml_model |
| 模型删除合约 | tests/services/test_ml_model_delete_contract.py | module_ml_model |
| 模型删除 API | tests/api/test_ml_model_delete_api.py | module_ml_model |
| 训练任务服务 | tests/services/test_model_training_job_service.py | module_ml_model |
| 训练任务 API | tests/api/test_ml_factor_training_job_api.py | module_ml_model |

## 数值软目标（M3 里程碑 review 时人工确认）
- 训练 AUC > 0.55（样本内，XGBoost 默认参数）
- feature importance 输出非空，无全零权重
- 模型持久化后可重新加载并预测

## 上游依赖
- feature_engineering 模块通过（有特征矩阵）

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_ml_model）
- [ ] 数值软目标：M3 里程碑 review 确认
