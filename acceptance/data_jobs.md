# 模块：data_jobs

## 职责
行情/财务数据下载入库，覆盖交易日历、股票基础信息、K线、财务报表，禁止 mock 数据进入真实路径。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| 任务运行器行为 | tests/data_jobs/test_runner.py | module_data_jobs |
| 任务 schema 校验 | tests/data_jobs/test_schemas.py | module_data_jobs |
| 任务服务逻辑 | tests/data_jobs/test_service.py | module_data_jobs |
| 去重逻辑 | tests/data_jobs/test_service_dedup.py | module_data_jobs |
| 执行模式切换 | tests/data_jobs/test_service_execution_mode.py | module_data_jobs |
| 注册表元数据 | tests/data_jobs/test_registry_metadata.py | module_data_jobs |
| 审计合约 | tests/data_jobs/test_audit_contract.py | module_data_jobs |
| 数据模型 | tests/data_jobs/test_models.py | module_data_jobs |
| 状态存储 | tests/data_jobs/test_state_store.py | module_data_jobs |
| 运行参数 | tests/data_jobs/test_runner_params.py | module_data_jobs |
| 注册表 | tests/data_jobs/test_registry.py | module_data_jobs |
| Celery 任务 | tests/data_jobs/test_celery_tasks.py | module_data_jobs |

## 数值软目标（里程碑 review 时人工确认）
- 无（数据下载模块以结构性合约为主，数值目标由下游模块负责）

## 上游依赖
- 无（数据入口模块）

## 验收状态
- [ ] 结构性合约：CI 绿（pytest -m module_data_jobs）
- [ ] 数值软目标：N/A
