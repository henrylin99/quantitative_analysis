# P0 Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove or isolate the most misleading demo behavior, fix misleading docs, and enforce env-driven configuration for the current production baseline.

**Architecture:** Treat P0 as a trust-restoration pass. Update user-facing docs and templates first to stop false signals, then tighten backend ML and realtime behavior so APIs and UI no longer silently downgrade to simulated behavior in production paths. Keep changes narrow and verifiable with targeted tests.

**Tech Stack:** Flask, SQLAlchemy, Jinja templates, pytest

---

### Task 1: Fix misleading project docs

**Files:**
- Modify: `README.md`
- Test: manual doc consistency review

**Step 1: Write the failing check**

Check that README still claims the project is complete and references `python app.py`.

**Step 2: Verify the check fails**

Run: `rg -n "功能完整|python app.py" README.md`

Expected: matches found.

**Step 3: Write minimal implementation**

Update README project positioning and startup instructions to match the current codebase and unfinished status.

**Step 4: Verify the check passes**

Run: `rg -n "功能完整|python app.py" README.md`

Expected: no misleading matches remain.

### Task 2: Stop auto-mock backtest fallback

**Files:**
- Modify: `app/templates/ml_factor/backtest.html`
- Test: `tests/ui/test_backtest_template_contract.py`

**Step 1: Write the failing test**

Assert the template no longer calls `displayMockResults()` in the failure path and does not define the old mock result helper.

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_backtest_template_contract.py -v`

Expected: FAIL because mock fallback still exists.

**Step 3: Write minimal implementation**

Replace fallback rendering with an explicit error/empty-state path and remove demo-only mock result generation from the production page.

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_backtest_template_contract.py -v`

Expected: PASS

### Task 3: Enforce real-training behavior in ML backend and API output

**Files:**
- Modify: `app/services/ml_models.py`
- Modify: `app/api/ml_factor_api.py`
- Test: `tests/services/test_ml_models_real_training_guard.py`
- Test: `tests/api/test_ml_factor_train_response_contract.py`

**Step 1: Write the failing tests**

Add one test asserting real training raises/returns an error when real target labels cannot be produced, and one API contract test asserting the training response no longer hardcodes demo values like `2.3MB`.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_ml_models_real_training_guard.py tests/api/test_ml_factor_train_response_contract.py -v`

Expected: FAIL against current behavior.

**Step 3: Write minimal implementation**

Remove silent simulated fallback from real training paths and make API responses reflect actual metrics only.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_ml_models_real_training_guard.py tests/api/test_ml_factor_train_response_contract.py -v`

Expected: PASS

### Task 4: Remove production-facing portfolio page fake data

**Files:**
- Modify: `app/templates/ml_factor/portfolio.html`
- Test: `tests/ui/test_portfolio_template_contract.py`

**Step 1: Write the failing test**

Assert the page no longer seeds hardcoded portfolio demo objects and instead surfaces a not-available or empty-state path.

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_portfolio_template_contract.py -v`

Expected: FAIL because hardcoded portfolio data still exists.

**Step 3: Write minimal implementation**

Replace fake portfolio bootstrap data with an empty-state or disabled message until backend CRUD is implemented.

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_portfolio_template_contract.py -v`

Expected: PASS

### Task 5: Disable legacy realtime mock minute ingestion

**Files:**
- Modify: `app/services/realtime_data_manager.py`
- Test: `tests/services/test_realtime_data_manager_production_guard.py`

**Step 1: Write the failing test**

Assert the legacy ingestion path does not generate random minute data and instead returns a clear unsupported/error result when no real source is configured.

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_realtime_data_manager_production_guard.py -v`

Expected: FAIL because legacy path still fabricates data.

**Step 3: Write minimal implementation**

Change the legacy path to refuse production-style sync without a real provider.

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_realtime_data_manager_production_guard.py -v`

Expected: PASS

### Task 6: Verify env-driven DB/Tushare config remains intact after merge

**Files:**
- Modify: `app/utils/db_utils.py` only if needed
- Test: `tests/services/test_db_utils_env_config.py`

**Step 1: Write the failing test**

Assert `DatabaseUtils` reads Tushare token from env and raises a clear error when missing.

**Step 2: Run test to verify it fails if needed**

Run: `pytest tests/services/test_db_utils_env_config.py -v`

Expected: PASS if current merged behavior is already correct; otherwise FAIL and implement.

**Step 3: Write minimal implementation**

Only if needed, align behavior with env-based configuration and explicit validation.

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_db_utils_env_config.py -v`

Expected: PASS
