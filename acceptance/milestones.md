# 里程碑验收清单

## M1：数据基础

**覆盖模块：** data_jobs

### 结构性门禁
- [ ] `pytest -m module_data_jobs` 全绿

### 数值软目标
- N/A

---

## M2：因子流水线

**覆盖模块：** factor_engine + feature_engineering

### 结构性门禁
- [ ] `pytest -m module_factor_engine` 全绿
- [ ] `pytest -m module_feature_engineering` 全绿

### 数值软目标（附日志截图）
- [ ] IC 均值 > 0.03，实测值：___
- [ ] IC_IR > 0.5，实测值：___
- [ ] 无全零或全 NaN 因子列：___

---

## M3：ML 流水线

**覆盖模块：** ml_model + scoring

### 结构性门禁
- [ ] `pytest -m module_ml_model` 全绿
- [ ] `pytest -m module_scoring` 全绿

### 数值软目标（附日志截图）
- [ ] 训练 AUC > 0.55，实测值：___
- [ ] feature importance 非空：___
- [ ] 打分覆盖率 > 80%，实测值：___

---

## M4：策略回测

**覆盖模块：** backtest + portfolio

### 结构性门禁
- [ ] `pytest -m module_backtest` 全绿
- [ ] `pytest -m module_portfolio` 全绿

### 数值软目标（附回测报告截图）
- [ ] Sharpe > 0.8，实测值：___
- [ ] 最大回撤 < 30%，实测值：___
- [ ] 年化收益 > 基准（沪深300），实测值：___
- [ ] 组合权重之和 = 1.0（误差 < 1e-6）：___
