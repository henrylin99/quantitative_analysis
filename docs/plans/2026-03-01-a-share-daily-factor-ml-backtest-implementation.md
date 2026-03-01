# A股日频多因子+机器学习+回测升级 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 8-12 周内完成 A股日频多因子、机器学习、组合优化与回测的可信闭环，并满足工程与策略双目标验收。

**Architecture:** 以现有 Flask + SQLAlchemy 项目为基础，优先修复回测可信度与数据口径，再补齐因子表达式、评分融合、滚动训练与全链路验证。核心业务逻辑下沉 service 层，API/UI 仅做编排与展示，结果以可复现元数据驱动。

**Tech Stack:** Python, Flask, SQLAlchemy, Pandas, NumPy, SciPy, CVXPY, scikit-learn, pytest

---

### Task 1: 建立测试基座与测试配置

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/services/test_smoke_app.py`
- Modify: `config.py`
- Test: `tests/services/test_smoke_app.py`

**Step 1: Write the failing test**

```python
def test_create_app_testing_config():
    from app import create_app
    app = create_app("testing")
    assert app.config["TESTING"] is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_smoke_app.py::test_create_app_testing_config -v`  
Expected: FAIL with `KeyError: 'testing'` or config missing.

**Step 3: Write minimal implementation**

```python
class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

config["testing"] = TestingConfig
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_smoke_app.py::test_create_app_testing_config -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add config.py tests/conftest.py tests/services/test_smoke_app.py
git commit -m "test: add testing config and smoke test for app factory"
```

---

### Task 2: 修复回测首日建仓与价格来源

**Files:**
- Modify: `app/services/backtest_engine.py`
- Create: `tests/services/test_backtest_initial_rebalance.py`
- Test: `tests/services/test_backtest_initial_rebalance.py`

**Step 1: Write the failing test**

```python
def test_initial_rebalance_uses_target_universe_prices(backtest_engine, monkeypatch):
    # 初始持仓为空，但目标股票有价格，期望首日完成建仓
    result = backtest_engine.run_backtest(
        {"factor_list": ["momentum_5d"], "top_n": 2},
        "2025-01-02", "2025-01-10", 1_000_000, "monthly"
    )
    assert result["success"] is True
    assert any(v["positions_value"] > 0 for v in result["portfolio_values"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_backtest_initial_rebalance.py::test_initial_rebalance_uses_target_universe_prices -v`  
Expected: FAIL with no position opened / positions_value remains 0.

**Step 3: Write minimal implementation**

```python
# 在回测循环中，先基于 selected_stocks 取价，再进行目标权重与再平衡
selected_codes = [s["ts_code"] for s in selected_stocks]
price_universe = list(set(selected_codes) | set(positions.keys()))
current_prices = self._get_current_prices(trade_date, price_universe)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_backtest_initial_rebalance.py::test_initial_rebalance_uses_target_universe_prices -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/backtest_engine.py tests/services/test_backtest_initial_rebalance.py
git commit -m "fix: ensure initial rebalance can open positions with target universe prices"
```

---

### Task 3: 固化回测时序（T日信号，T+1开盘成交）

**Files:**
- Modify: `app/services/backtest_engine.py`
- Create: `tests/services/test_backtest_tplus1_execution.py`
- Test: `tests/services/test_backtest_tplus1_execution.py`

**Step 1: Write the failing test**

```python
def test_signal_generated_on_t_executed_on_t_plus_1(backtest_engine):
    result = backtest_engine.run_backtest(
        {"factor_list": ["momentum_1d"], "top_n": 3},
        "2025-01-02", "2025-01-15", 1_000_000, "weekly"
    )
    assert result["success"] is True
    # 验证首个调仓日不直接按同日价格成交
    assert result["portfolio_values"][0]["positions_value"] == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_backtest_tplus1_execution.py::test_signal_generated_on_t_executed_on_t_plus_1 -v`  
Expected: FAIL because same-day execution still occurs.

**Step 3: Write minimal implementation**

```python
# 将 trade_dates 分为 signal_date 和 execution_date 配对
for i in range(len(trade_dates) - 1):
    signal_date = trade_dates[i]
    execution_date = trade_dates[i + 1]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_backtest_tplus1_execution.py::test_signal_generated_on_t_executed_on_t_plus_1 -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/backtest_engine.py tests/services/test_backtest_tplus1_execution.py
git commit -m "feat: enforce T+1 execution policy in backtest engine"
```

---

### Task 4: 实现基准收益（沪深300）与策略对比

**Files:**
- Modify: `app/services/backtest_engine.py`
- Create: `tests/services/test_backtest_benchmark_returns.py`
- Test: `tests/services/test_backtest_benchmark_returns.py`

**Step 1: Write the failing test**

```python
def test_backtest_returns_include_non_empty_benchmark(backtest_engine):
    result = backtest_engine.run_backtest(
        {"factor_list": ["momentum_5d"], "top_n": 5},
        "2025-01-02", "2025-03-31", 1_000_000, "monthly"
    )
    assert result["success"] is True
    assert len(result["benchmark_returns"]) > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_backtest_benchmark_returns.py::test_backtest_returns_include_non_empty_benchmark -v`  
Expected: FAIL because benchmark is empty list.

**Step 3: Write minimal implementation**

```python
# 使用固定 ts_code（如 "000300.SH"）读取 StockDailyHistory 计算基准收益
benchmark_prices = ...
benchmark_returns = ...
return benchmark_returns
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_backtest_benchmark_returns.py::test_backtest_returns_include_non_empty_benchmark -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/backtest_engine.py tests/services/test_backtest_benchmark_returns.py
git commit -m "feat: add HS300 benchmark returns in backtest results"
```

---

### Task 5: 实现可交易性与异常策略（停牌/缺价/涨跌停）

**Files:**
- Modify: `app/services/backtest_engine.py`
- Create: `tests/services/test_backtest_tradability.py`
- Test: `tests/services/test_backtest_tradability.py`

**Step 1: Write the failing test**

```python
def test_untradable_stocks_are_deferred_and_logged(backtest_engine):
    result = backtest_engine.run_backtest(
        {"factor_list": ["momentum_20d"], "top_n": 3},
        "2025-02-01", "2025-02-28", 1_000_000, "weekly"
    )
    assert result["success"] is True
    assert "execution_notes" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_backtest_tradability.py::test_untradable_stocks_are_deferred_and_logged -v`  
Expected: FAIL because no tradability notes exist.

**Step 3: Write minimal implementation**

```python
# 增加 _is_tradable(...) 判断，失败时记录 execution_notes
if not self._is_tradable(ts_code, trade_date, price):
    execution_notes.append({"ts_code": ts_code, "reason": "untradable"})
    continue
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_backtest_tradability.py::test_untradable_stocks_are_deferred_and_logged -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/backtest_engine.py tests/services/test_backtest_tradability.py
git commit -m "feat: add tradability checks and execution notes in backtest"
```

---

### Task 6: 完成自定义因子表达式引擎（安全白名单）

**Files:**
- Create: `app/services/factor_expression_engine.py`
- Modify: `app/services/factor_engine.py`
- Create: `tests/services/test_factor_expression_engine.py`
- Test: `tests/services/test_factor_expression_engine.py`

**Step 1: Write the failing test**

```python
def test_custom_factor_expression_pct_change_and_rolling_mean(engine, sample_df):
    expr = "close.pct_change(5).rolling(20).mean()"
    out = engine.evaluate(expr, sample_df)
    assert out.notna().sum() > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_factor_expression_engine.py::test_custom_factor_expression_pct_change_and_rolling_mean -v`  
Expected: FAIL with `AttributeError` or evaluator missing.

**Step 3: Write minimal implementation**

```python
ALLOWED_FUNCS = {"pct_change", "rolling", "mean", "std", "rank"}
def evaluate(self, expr, df):
    # ast 解析 + 白名单节点校验 + 安全执行上下文
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_factor_expression_engine.py::test_custom_factor_expression_pct_change_and_rolling_mean -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/factor_expression_engine.py app/services/factor_engine.py tests/services/test_factor_expression_engine.py
git commit -m "feat: implement safe custom factor expression engine"
```

---

### Task 7: 实现 RankIC 动态加权评分

**Files:**
- Modify: `app/services/stock_scoring.py`
- Create: `tests/services/test_rank_ic_scoring.py`
- Test: `tests/services/test_rank_ic_scoring.py`

**Step 1: Write the failing test**

```python
def test_rank_ic_scoring_uses_historical_ic_weights(scoring_engine, factor_scores):
    scores = scoring_engine.calculate_composite_score(
        factor_scores, {"momentum_5d": 0.5, "roe_ttm": 0.5}, method="rank_ic"
    )
    assert "composite_score" in scores.columns
    assert scores["composite_score"].std() > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_rank_ic_scoring.py::test_rank_ic_scoring_uses_historical_ic_weights -v`  
Expected: FAIL because method still returns equal-weight placeholder.

**Step 3: Write minimal implementation**

```python
def _rank_ic_scoring(self, factor_scores, weights):
    ic_weights = self._load_factor_rank_ic_weights(...)
    ic_weights = ic_weights / ic_weights.sum()
    return (factor_scores * ic_weights).sum(axis=1)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_rank_ic_scoring.py::test_rank_ic_scoring_uses_historical_ic_weights -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/stock_scoring.py tests/services/test_rank_ic_scoring.py
git commit -m "feat: implement rank-ic weighted stock scoring"
```

---

### Task 8: 实现多模型集成评分（ML Ensemble）

**Files:**
- Modify: `app/services/stock_scoring.py`
- Create: `tests/services/test_ml_ensemble_scoring.py`
- Test: `tests/services/test_ml_ensemble_scoring.py`

**Step 1: Write the failing test**

```python
def test_ml_ensemble_scoring_aggregates_model_predictions(scoring_engine):
    df = scoring_engine._ensemble_predictions(
        predictions=..., method="performance_weighted"
    )
    assert "ensemble_score" in df.columns
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_ml_ensemble_scoring.py::test_ml_ensemble_scoring_aggregates_model_predictions -v`  
Expected: FAIL because ensemble remains placeholder path.

**Step 3: Write minimal implementation**

```python
def _ml_ensemble_scoring(self, factor_scores, weights):
    model_scores = self._load_latest_model_predictions(...)
    aligned = factor_scores.join(model_scores, how="left").fillna(0)
    return aligned["ensemble_score"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_ml_ensemble_scoring.py::test_ml_ensemble_scoring_aggregates_model_predictions -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/stock_scoring.py tests/services/test_ml_ensemble_scoring.py
git commit -m "feat: add model ensemble scoring pipeline"
```

---

### Task 9: 建立“打分->预期收益”映射并接入组合优化

**Files:**
- Modify: `app/services/backtest_engine.py`
- Modify: `app/services/portfolio_optimizer.py`
- Create: `tests/services/test_expected_return_mapping.py`
- Test: `tests/services/test_expected_return_mapping.py`

**Step 1: Write the failing test**

```python
def test_expected_return_mapping_monotonic(backtest_engine):
    mapped = backtest_engine._map_score_to_expected_return(
        {"A": 2.0, "B": 1.0, "C": -1.0}
    )
    assert mapped["A"] > mapped["B"] > mapped["C"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_expected_return_mapping.py::test_expected_return_mapping_monotonic -v`  
Expected: FAIL because mapper does not exist.

**Step 3: Write minimal implementation**

```python
def _map_score_to_expected_return(self, score_dict):
    # z-score -> clipped expected returns
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_expected_return_mapping.py::test_expected_return_mapping_monotonic -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/backtest_engine.py app/services/portfolio_optimizer.py tests/services/test_expected_return_mapping.py
git commit -m "feat: map selection scores to expected returns for optimizer input"
```

---

### Task 10: 落地 Walk-Forward 训练与验证流程

**Files:**
- Modify: `app/services/ml_models.py`
- Create: `tests/services/test_walk_forward_training.py`
- Test: `tests/services/test_walk_forward_training.py`

**Step 1: Write the failing test**

```python
def test_walk_forward_splits_are_time_ordered(ml_manager):
    splits = ml_manager._build_walk_forward_splits("2023-01-01", "2024-12-31")
    assert all(s["train_end"] < s["test_start"] for s in splits)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_walk_forward_training.py::test_walk_forward_splits_are_time_ordered -v`  
Expected: FAIL because split builder does not exist.

**Step 3: Write minimal implementation**

```python
def _build_walk_forward_splits(self, start_date, end_date, train_months=24, test_months=3):
    # 生成滚动时间窗
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_walk_forward_training.py::test_walk_forward_splits_are_time_ordered -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/ml_models.py tests/services/test_walk_forward_training.py
git commit -m "feat: add walk-forward split builder for model training"
```

---

### Task 11: 建立端到端链路集成测试与结果快照

**Files:**
- Create: `tests/integration/test_research_pipeline_e2e.py`
- Create: `tests/fixtures/pipeline_snapshot.json`
- Modify: `app/api/ml_factor_api.py`
- Test: `tests/integration/test_research_pipeline_e2e.py`

**Step 1: Write the failing test**

```python
def test_e2e_pipeline_returns_metrics(client):
    resp = client.post("/api/ml-factor/backtest/run", json={...})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "performance_metrics" in data["results"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_research_pipeline_e2e.py::test_e2e_pipeline_returns_metrics -v`  
Expected: FAIL due response schema mismatch or missing fields.

**Step 3: Write minimal implementation**

```python
# 统一 backtest API 响应字段：success/results/errors/meta
return jsonify({"success": True, "results": result, "meta": {...}})
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_research_pipeline_e2e.py::test_e2e_pipeline_returns_metrics -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/ml_factor_api.py tests/integration/test_research_pipeline_e2e.py tests/fixtures/pipeline_snapshot.json
git commit -m "test: add end-to-end pipeline integration test and stabilize API schema"
```

---

### Task 12: 配置安全化与文档统一

**Files:**
- Modify: `app/utils/db_utils.py`
- Modify: `README.md`
- Modify: `run.py`
- Modify: `run_system.py`
- Create: `.env.example`
- Test: `tests/services/test_smoke_app.py`

**Step 1: Write the failing test**

```python
def test_no_hardcoded_secret_in_db_utils():
    content = Path("app/utils/db_utils.py").read_text(encoding="utf-8")
    assert "93aaf3f9" not in content
    assert "_password = 'root'" not in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_smoke_app.py::test_no_hardcoded_secret_in_db_utils -v`  
Expected: FAIL because token/password are currently hardcoded.

**Step 3: Write minimal implementation**

```python
_host = os.getenv("DB_HOST", "localhost")
_user = os.getenv("DB_USER", "root")
_password = os.getenv("DB_PASSWORD", "")
_tushare_token = os.getenv("TUSHARE_TOKEN", "")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_smoke_app.py::test_no_hardcoded_secret_in_db_utils -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/utils/db_utils.py README.md run.py run_system.py .env.example tests/services/test_smoke_app.py
git commit -m "chore: remove hardcoded credentials and unify startup docs"
```

---

## 全局执行规则

- 每个任务执行前使用 `@superpowers:test-driven-development`
- 每个任务完成前使用 `@superpowers:verification-before-completion`
- 任务实现阶段使用 `@superpowers:systematic-debugging` 处理失败
- 任务实现完成后进行一次 `@superpowers:requesting-code-review`

## 里程碑映射

- Week 1-2: Task 1-5
- Week 3-4: Task 6
- Week 5-6: Task 10
- Week 7-8: Task 7-9
- Week 9-10: Task 11-12
- Week 11-12: 缓冲与指标调优（仅在前序任务全部完成后启用）
