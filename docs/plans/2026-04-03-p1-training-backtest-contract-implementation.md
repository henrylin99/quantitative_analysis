# P1 Training And Backtest Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace fake frontend training progress with backend-driven task status, and align backtest API responses with the fields consumed by the backtest UI.

**Architecture:** Introduce a lightweight backend training job service that tracks real execution stages and exposes polling snapshots to the models UI. For backtests, move chart/result shaping into the backend so the UI renders explicit response fields instead of deriving business metrics from partial payloads.

**Tech Stack:** Flask, SQLAlchemy, Jinja/JavaScript, pytest

---

### Task 1: Add training job API contract tests

**Files:**
- Create: `tests/api/test_ml_factor_training_job_api.py`
- Modify: `app/api/ml_factor_api.py`

**Step 1: Write the failing tests**

Add tests for:
- `POST /api/ml-factor/models/train` returns a backend job id and queued/running status instead of immediate fake success metrics
- `GET /api/ml-factor/models/train-jobs/<job_id>` returns a polling snapshot

**Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_ml_factor_training_job_api.py -v`

Expected: FAIL because the endpoints/contract do not exist yet.

**Step 3: Write minimal implementation**

Add training job submission and polling endpoints.

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_ml_factor_training_job_api.py -v`

Expected: PASS

### Task 2: Add backend training job service and wire real stage updates

**Files:**
- Create: `app/services/model_training_job_service.py`
- Modify: `app/services/ml_models.py`
- Test: `tests/services/test_model_training_job_service.py`

**Step 1: Write the failing test**

Add a service test asserting a submitted job produces a snapshot with status, progress, logs, and result/error fields, and that progress updates are callback-driven.

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_model_training_job_service.py -v`

Expected: FAIL because the service does not exist yet.

**Step 3: Write minimal implementation**

Implement a lightweight in-process training job service and add optional progress callbacks inside `MLModelManager.train_model`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_model_training_job_service.py -v`

Expected: PASS

### Task 3: Replace fake training progress in the models UI

**Files:**
- Modify: `app/templates/ml_factor/models.html`
- Test: `tests/ui/test_models_training_polling_contract.py`

**Step 1: Write the failing test**

Assert the template no longer uses random progress simulation and instead references backend polling logic for a training job id.

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_models_training_polling_contract.py -v`

Expected: FAIL because the template still uses `setInterval` random progress.

**Step 3: Write minimal implementation**

Update the training modal flow to submit a job, poll backend snapshots, render real logs/progress, and show final metrics from the finished job.

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_models_training_polling_contract.py -v`

Expected: PASS

### Task 4: Add backtest response contract tests

**Files:**
- Create: `tests/services/test_backtest_response_contract.py`
- Create: `tests/api/test_backtest_run_contract.py`
- Modify: `app/services/backtest_engine.py`
- Modify: `app/api/ml_factor_api.py`

**Step 1: Write the failing tests**

Add tests asserting the backtest engine/API return:
- `performance_metrics.annual_return`
- `benchmark_returns[*].value`
- explicit `industry_distribution`
- explicit `positions`
- explicit `risk_metrics`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_backtest_response_contract.py tests/api/test_backtest_run_contract.py -v`

Expected: FAIL because the response is still partial and mismatched.

**Step 3: Write minimal implementation**

Shape the backtest engine output to include UI-ready fields.

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_backtest_response_contract.py tests/api/test_backtest_run_contract.py -v`

Expected: PASS

### Task 5: Simplify the backtest UI to consume backend schema

**Files:**
- Modify: `app/templates/ml_factor/backtest.html`
- Test: `tests/ui/test_backtest_backend_schema_contract.py`

**Step 1: Write the failing test**

Assert the template consumes backend-provided fields instead of inventing benchmark, industry, or position metrics in the browser.

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_backtest_backend_schema_contract.py -v`

Expected: FAIL because the template still derives business fields locally.

**Step 3: Write minimal implementation**

Update the page to render `data.positions`, `data.risk_metrics`, and aligned benchmark values from backend output.

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_backtest_backend_schema_contract.py -v`

Expected: PASS
