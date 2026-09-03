# 模块：trial

## 职责
试用功能的只读数据面板：每日市场简报、财务健康度、资金流统计、个股雷达/全景、板块热力图。
Flask 页面路由与 `/api/trial/*` JSON API 共用 `app/services/trial_analytics.py` 的 payload 计算，两端不重复实现。

## 结构性合约（自动，硬门禁）
| 合约 | 测试文件 | Marker |
|---|---|---|
| trial API 信封与错误码合约 | tests/api/test_trial_api_contract.py | module_trial |

## 数值软目标
- 只读端点：无写入副作用；数据缺失时返回空结构而非报错退出

## 上游依赖
- trial_analytics / heatmap_service（数据缺失时降级为空 payload）

## 验收状态
- [x] 结构性合约：pytest -m module_trial
