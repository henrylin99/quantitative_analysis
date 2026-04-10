# 模块：scoring

## 职责
基于因子权重和 ML 模型对股票打分，输出排序结果，支持因子打分和 ML 打分两种模式。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| 打分方法合约 | tests/services/test_stock_scoring_methods.py | module_scoring |
| 打分模板 UI 合约 | tests/ui/test_scoring_template_contract.py | module_scoring |
| 打分入口 UI 合约 | tests/ui/test_model_and_scoring_entry_copy_contract.py | module_scoring |

## 数值软目标（M3 里程碑 review 时人工确认）
- 打分输出覆盖率 > 80%（有效打分股票数 / 股票池总数）
- 打分结果无 NaN，分布合理（非全相同分值）

## 上游依赖
- factor_engine 模块通过
- ml_model 模块通过（ML 打分模式）

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_scoring）
- [ ] 数值软目标：M3 里程碑 review 确认
