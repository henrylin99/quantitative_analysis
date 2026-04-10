# 模块：portfolio

## 职责
等权、均值方差、风险平价、因子中性四种组合优化算法，输出权重向量，支持约束条件（持仓上下限、行业中性等）。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| 方法守卫 | tests/api/test_portfolio_method_guard.py | module_portfolio |
| 约束条件守卫 | tests/api/test_portfolio_constraint_guard.py | module_portfolio |
| Black-Litterman | tests/services/test_portfolio_black_litterman.py | module_portfolio |
| 因子中性 | tests/services/test_portfolio_factor_neutral.py | module_portfolio |
| 只读 API | tests/api/test_portfolio_readonly_api.py | module_portfolio |
| 删除 API | tests/api/test_portfolio_delete_api.py | module_portfolio |
| 保存优化结果 API | tests/api/test_portfolio_save_optimized_api.py | module_portfolio |
| 创建 API | tests/api/test_portfolio_create_api.py | module_portfolio |
| 持仓更新 API | tests/api/test_portfolio_position_update_api.py | module_portfolio |
| 再平衡 API | tests/api/test_portfolio_rebalance_api.py | module_portfolio |
| 批量再平衡 API | tests/api/test_portfolio_rebalance_batch_api.py | module_portfolio |
| 支持方法 UI 合约 | tests/ui/test_portfolio_supported_methods_contract.py | module_portfolio |
| 组合模板 UI 合约 | tests/ui/test_portfolio_template_contract.py | module_portfolio |

## 数值软目标（M4 里程碑 review 时人工确认）
- 权重之和 = 1.0（误差 < 1e-6）
- 无权重 < 0（无卖空约束模式下）
- 均值方差优化收敛（无 cvxpy INFEASIBLE 状态）

## 上游依赖
- backtest 模块通过
- scoring 模块通过

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_portfolio）
- [ ] 数值软目标：M4 里程碑 review 确认
