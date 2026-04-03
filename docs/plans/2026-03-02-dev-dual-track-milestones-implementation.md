# Dev Dual-Track Milestones (4 Weeks) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 4 周内并行完成数据任务中心生产化增强与策略主链路关键能力补齐，形成可运营、可验证的双轨交付。

**Architecture:** 以 `data_jobs` 现有架构为基础，先补齐任务治理与可观测能力；策略侧围绕 `BacktestEngine -> FactorEngine -> StockScoringEngine -> PortfolioOptimizer` 逐步替换占位实现。所有增量遵循 TDD（先写失败测试，再最小实现）和小步提交。

**Tech Stack:** Flask, SQLAlchemy, Celery, Redis, Pandas, NumPy, scikit-learn, CVXPY, pytest

---

### Task 1: API错误码分级与任务类型校验

**Files:**
- Modify: `app/api/data_jobs_api.py`
- Create: `tests/api/test_data_jobs_api_error_codes.py`
- Test: `tests/api/test_data_jobs_api_error_codes.py`

**Step 1: Write the failing test**

```python
def test_submit_unknown_job_returns_400(client):
    resp = client.post('/api/data-jobs/submit', json={'job_type': 'unknown_job'})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_data_jobs_api_error_codes.py::test_submit_unknown_job_returns_400 -v`
Expected: FAIL with status code `500`.

**Step 3: Write minimal implementation**

```python
# in submit_job()
except KeyError as exc:
    return jsonify({'success': False, 'error': str(exc)}), 400
except ValueError as exc:
    return jsonify({'success': False, 'error': str(exc)}), 400
except Exception as exc:
    return jsonify({'success': False, 'error': str(exc)}), 500
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_data_jobs_api_error_codes.py::test_submit_unknown_job_returns_400 -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/api/data_jobs_api.py tests/api/test_data_jobs_api_error_codes.py
git commit -m "fix: return 400 for invalid data job submissions"
```

### Task 2: 数据任务运行历史分页与状态过滤

**Files:**
- Modify: `app/services/data_jobs/service.py`
- Modify: `app/api/data_jobs_api.py`
- Create: `tests/api/test_data_jobs_api_list_filters.py`
- Test: `tests/api/test_data_jobs_api_list_filters.py`

**Step 1: Write the failing test**

```python
def test_list_runs_supports_status_filter(client, seed_runs):
    resp = client.get('/api/data-jobs/list?status=failed&limit=10')
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(run['status'] == 'failed' for run in data['runs'])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_data_jobs_api_list_filters.py::test_list_runs_supports_status_filter -v`
Expected: FAIL because `status` query is ignored.

**Step 3: Write minimal implementation**

```python
# service.py
def list_runs(self, limit=50, status=None):
    query = DataJobRun.query.order_by(DataJobRun.id.desc())
    if status:
        query = query.filter(DataJobRun.status == status)
    return query.limit(limit).all()

# api.py
status = request.args.get('status')
runs = service.list_runs(limit=limit, status=status)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_data_jobs_api_list_filters.py::test_list_runs_supports_status_filter -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/data_jobs/service.py app/api/data_jobs_api.py tests/api/test_data_jobs_api_list_filters.py
git commit -m "feat: add status filter for data job run listing"
```

### Task 3: 任务去重/互斥（同job_type + 同参数）

**Files:**
- Modify: `app/services/data_jobs/service.py`
- Create: `tests/data_jobs/test_service_dedup.py`
- Test: `tests/data_jobs/test_service_dedup.py`

**Step 1: Write the failing test**

```python
def test_submit_same_job_and_params_is_rejected(service, running_run):
    with pytest.raises(ValueError):
        service.submit('stock_basic', {'start_date': '20260101'})
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_service_dedup.py::test_submit_same_job_and_params_is_rejected -v`
Expected: FAIL because duplicate submission is currently allowed.

**Step 3: Write minimal implementation**

```python
# service.py
existing = DataJobRun.query.filter(
    DataJobRun.job_type == job_type,
    DataJobRun.status.in_(['pending', 'queued', 'running']),
    DataJobRun.params_json == (params or {})
).first()
if existing:
    raise ValueError(f'duplicate running job: {existing.id}')
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_service_dedup.py::test_submit_same_job_and_params_is_rejected -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/data_jobs/service.py tests/data_jobs/test_service_dedup.py
git commit -m "feat: prevent duplicate queued/running data jobs"
```

### Task 4: 回测基准收益（HS300）实现

**Files:**
- Modify: `app/services/backtest_engine.py`
- Create: `tests/services/test_backtest_benchmark_returns.py`
- Test: `tests/services/test_backtest_benchmark_returns.py`

**Step 1: Write the failing test**

```python
def test_backtest_contains_non_empty_benchmark(backtest_engine):
    result = backtest_engine.run_backtest(
        {'factor_list': ['momentum_5d'], 'top_n': 5},
        '2025-01-02', '2025-03-31', 1_000_000, 'monthly'
    )
    assert result.get('success') is True
    assert len(result.get('benchmark_returns', [])) > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_backtest_benchmark_returns.py::test_backtest_contains_non_empty_benchmark -v`
Expected: FAIL because `_get_benchmark_returns` returns `[]`.

**Step 3: Write minimal implementation**

```python
# backtest_engine.py
query = db.session.query(StockDailyHistory.trade_date, StockDailyHistory.close).filter(
    StockDailyHistory.ts_code == '000300.SH',
    StockDailyHistory.trade_date >= start_date,
    StockDailyHistory.trade_date <= end_date
).order_by(StockDailyHistory.trade_date)
# compute daily pct returns and cumulative return series
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_backtest_benchmark_returns.py::test_backtest_contains_non_empty_benchmark -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/backtest_engine.py tests/services/test_backtest_benchmark_returns.py
git commit -m "feat: add HS300 benchmark returns in backtest"
```

### Task 5: 自定义因子表达式MVP（白名单函数）

**Files:**
- Create: `app/services/factor_expression_engine.py`
- Modify: `app/services/factor_engine.py`
- Create: `tests/services/test_factor_expression_engine.py`
- Test: `tests/services/test_factor_expression_engine.py`

**Step 1: Write the failing test**

```python
def test_expression_engine_supports_pct_change_and_rolling_mean(expr_engine, sample_df):
    out = expr_engine.evaluate('close.pct_change(5) - close.rolling(20).mean()', sample_df)
    assert 'factor_value' in out.columns
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_factor_expression_engine.py::test_expression_engine_supports_pct_change_and_rolling_mean -v`
Expected: FAIL with `ModuleNotFoundError` or unimplemented behavior.

**Step 3: Write minimal implementation**

```python
# factor_expression_engine.py
ALLOWED_FUNCS = {'pct_change', 'rolling', 'mean', 'std', 'shift', 'rank'}
# parse expression safely and evaluate against DataFrame columns
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_factor_expression_engine.py::test_expression_engine_supports_pct_change_and_rolling_mean -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/factor_expression_engine.py app/services/factor_engine.py tests/services/test_factor_expression_engine.py
git commit -m "feat: add safe custom factor expression engine"
```

### Task 6: ML集成评分与RankIC动态权重评分

**Files:**
- Modify: `app/services/stock_scoring.py`
- Create: `tests/services/test_stock_scoring_methods.py`
- Test: `tests/services/test_stock_scoring_methods.py`

**Step 1: Write the failing test**

```python
def test_rank_ic_scoring_uses_dynamic_weights(engine, factor_scores):
    scores = engine.calculate_composite_score(factor_scores, weights={}, method='rank_ic')
    assert not scores.empty
    assert 'composite_score' in scores.columns
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_stock_scoring_methods.py::test_rank_ic_scoring_uses_dynamic_weights -v`
Expected: FAIL because method currently falls back to equal-weight placeholder.

**Step 3: Write minimal implementation**

```python
# stock_scoring.py
# 1) estimate historical rank ic per factor
# 2) normalize to non-negative weights
# 3) compute weighted cross-sectional score
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_stock_scoring_methods.py::test_rank_ic_scoring_uses_dynamic_weights -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/stock_scoring.py tests/services/test_stock_scoring_methods.py
git commit -m "feat: implement ml ensemble and rank-ic based scoring"
```

### Task 7: 因子中性优化首版落地

**Files:**
- Modify: `app/services/portfolio_optimizer.py`
- Create: `tests/services/test_portfolio_factor_neutral.py`
- Test: `tests/services/test_portfolio_factor_neutral.py`

**Step 1: Write the failing test**

```python
def test_factor_neutral_weights_control_exposure(optimizer, expected_returns, risk_model, exposures):
    result = optimizer.optimize_portfolio(
        expected_returns,
        risk_model=risk_model,
        method='factor_neutral',
        constraints={'factor_exposures': exposures, 'exposure_tolerance': 1e-3}
    )
    assert result.get('success') is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_portfolio_factor_neutral.py::test_factor_neutral_weights_control_exposure -v`
Expected: FAIL because current method only proxies mean-variance.

**Step 3: Write minimal implementation**

```python
# portfolio_optimizer.py
# add cvxpy constraints: abs(F.T @ w) <= tolerance
# keep sum(w)=1 and w>=0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_portfolio_factor_neutral.py::test_factor_neutral_weights_control_exposure -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/portfolio_optimizer.py tests/services/test_portfolio_factor_neutral.py
git commit -m "feat: implement factor-neutral optimization constraints"
```

### Task 8: 数据任务中心UI增强（历史、轮询、日志）

**Files:**
- Modify: `app/static/js/data_jobs.js`
- Modify: `app/templates/realtime_analysis/index.html`
- Create: `tests/ui/test_data_jobs_ui_progress_contract.py`
- Test: `tests/ui/test_data_jobs_ui_progress_contract.py`

**Step 1: Write the failing test**

```python
def test_data_jobs_page_contains_run_history_and_progress_blocks():
    html = Path('app/templates/realtime_analysis/index.html').read_text(encoding='utf-8')
    assert 'dataJobHistory' in html
    assert 'dataJobProgress' in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_data_jobs_ui_progress_contract.py::test_data_jobs_page_contains_run_history_and_progress_blocks -v`
Expected: FAIL because these blocks do not exist yet.

**Step 3: Write minimal implementation**

```javascript
// data_jobs.js
// add polling by run_id -> GET /api/data-jobs/<id>
// render progress/status/logs
// add history loader -> GET /api/data-jobs/list
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_data_jobs_ui_progress_contract.py::test_data_jobs_page_contains_run_history_and_progress_blocks -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/static/js/data_jobs.js app/templates/realtime_analysis/index.html tests/ui/test_data_jobs_ui_progress_contract.py
git commit -m "feat: add data job progress polling and run history ui"
```

### Task 9: 回归测试与文档收口

**Files:**
- Modify: `docs/guides/data_jobs_user_guide.md`
- Modify: `README.md`
- Create: `tests/regression/test_dual_track_smoke.py`
- Test: `tests/regression/test_dual_track_smoke.py`

**Step 1: Write the failing test**

```python
def test_dual_track_core_endpoints_registered(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert '/api/data-jobs/submit' in rules
    assert '/api/ml-factor/backtest/run' in rules
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/regression/test_dual_track_smoke.py::test_dual_track_core_endpoints_registered -v`
Expected: FAIL if test app fixture is missing route registration.

**Step 3: Write minimal implementation**

```python
# add fixture in tests/conftest.py using create_app('development')
# ensure app context and route map available
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/regression/test_dual_track_smoke.py::test_dual_track_core_endpoints_registered -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/regression/test_dual_track_smoke.py tests/conftest.py docs/guides/data_jobs_user_guide.md README.md
git commit -m "test: add dual-track smoke regression and update docs"
```

### Task 10: 全量验证与发布前检查

**Files:**
- Modify: `scripts/validation/validate_data_jobs_flow.sh`
- Test: `tests/data_jobs/*`, `tests/api/*`, `tests/ui/*`, `tests/services/*`, `tests/regression/*`

**Step 1: Write the failing check case**

```bash
# Add one negative check for unknown job type returning 400
curl -sS -X POST "$BASE_URL/api/data-jobs/submit" -H 'Content-Type: application/json' -d '{"job_type":"unknown"}'
```

**Step 2: Run validation to verify it fails (before script update)**

Run: `bash scripts/validation/validate_data_jobs_flow.sh http://127.0.0.1:5001`
Expected: FAIL because negative path not yet asserted.

**Step 3: Write minimal implementation**

```bash
# validate_data_jobs_flow.sh
# 1) assert /jobs and /list success
# 2) assert unknown job submit returns success=false
# 3) output clear pass/fail summary
```

**Step 4: Run test suite to verify it passes**

Run: `pytest tests/data_jobs tests/api tests/ui tests/services tests/regression -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/validation/validate_data_jobs_flow.sh
git commit -m "chore: strengthen validation script for dual-track release checks"
```

---

## Notes
- 执行顺序建议：Task 1 -> 2 -> 3（工程轨W1/W2）并行 Task 4 -> 5（策略轨W1/W2），后续按周推进。
- 参考技能：`@superpowers:test-driven-development`、`@superpowers:verification-before-completion`、`@superpowers:requesting-code-review`。
- 每个任务完成后都要执行对应测试并保存关键输出摘要到操作日志。
