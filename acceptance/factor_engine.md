# 模块：factor_engine

## 职责
计算内置因子（PE、PB、动量、成长等）和自定义因子表达式，输出标准化因子 DataFrame，禁止 mock/demo 数据进入真实路径。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| 自定义因子白名单校验 | tests/services/test_factor_engine_custom_factor_validation.py | module_factor_engine |
| 内置因子样本验证 | tests/services/test_builtin_factor_validation_samples.py | module_factor_engine |
| 自定义因子 API 合约 | tests/api/test_custom_factor_contract.py | module_factor_engine |
| 内置因子样本 API | tests/api/test_builtin_factor_validation_samples_api.py | module_factor_engine |

## 数值软目标（M2 里程碑 review 时人工确认）
- IC 均值 > 0.03（样本期内，至少 3 个因子）
- IC_IR > 0.5（IC均值 / IC标准差）
- 无全零或全 NaN 因子列

## 上游依赖
- data_jobs 模块通过（有真实行情数据入库）

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_factor_engine）
- [ ] 数值软目标：M2 里程碑 review 确认
