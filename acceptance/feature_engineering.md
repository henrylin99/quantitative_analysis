# 模块：feature_engineering

## 职责
因子表达式引擎、IC/IR 校验、因子组合与特征构建，为 ML 训练提供输入。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| 因子表达式引擎 | tests/services/test_factor_expression_engine.py | module_feature_engineering |
| ML 因子训练响应合约 | tests/api/test_ml_factor_train_response_contract.py | module_feature_engineering |
| 因子管理 UI 合约 | tests/ui/test_factor_management_contract.py | module_feature_engineering |

## 数值软目标（M2 里程碑 review 时人工确认）
- IC 均值 > 0.03（特征选择后保留因子）
- 因子表达式解析无报错，输出 shape 正确

## 上游依赖
- factor_engine 模块通过

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_feature_engineering）
- [ ] 数值软目标：M2 里程碑 review 确认
