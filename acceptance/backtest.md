# 模块：backtest

## 职责
单策略和多策略回测，计算收益、Sharpe、最大回撤等指标，使用真实行情数据，禁止 mock 默认值。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| 基准收益计算 | tests/services/test_backtest_benchmark_returns.py | module_backtest |
| 回测响应合约 | tests/services/test_backtest_response_contract.py | module_backtest |
| 无 fake 默认值守卫 | tests/ui/test_backtest_template_no_fake_defaults.py | module_backtest |
| 回测模板 UI 合约 | tests/ui/test_backtest_template_contract.py | module_backtest |
| 回测 schema 合约 | tests/ui/test_backtest_backend_schema_contract.py | module_backtest |
| 回测执行合约 | tests/ui/test_backtest_execution_contract.py | module_backtest |

## 数值软目标（M4 里程碑 review 时人工确认）
- 样本内 Sharpe > 0.8（单因子策略，2年回测）
- 最大回撤 < 30%
- 年化收益 > 基准（沪深300）

## 上游依赖
- factor_engine 模块通过（因子策略）或 ml_model 模块通过（ML 策略）
- data_jobs 模块通过（真实行情数据）

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_backtest）
- [ ] 数值软目标：M4 里程碑 review 确认
