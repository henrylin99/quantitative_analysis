# ML Factor Scoring Date Source Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the scoring page auto-load the latest factor date in factor mode and the latest prediction date in ML mode.

**Architecture:** Keep the existing factor-date lookup for factor-based scoring. Add a separate backend lookup for the latest available prediction date, derived from the persisted model prediction table. On the frontend, switch the date source when the scoring method changes so the date field always matches the active scoring path.

**Tech Stack:** Flask blueprints, pandas, Jinja2 templates, pytest, existing parquet-backed repositories.

---

### Task 1: Add backend lookup for latest prediction date

**Files:**
- Modify: `app/api/ml_factor_api.py`
- Test: `tests/api/test_ml_factor_model_contract.py`

**Step 1: Write the failing test**

Add a route test that patches the ML manager with a temporary parquet store containing prediction rows and asserts:
- `GET /api/ml-factor/scoring/latest-prediction-date` returns `200`
- the JSON contains `success: true`
- the latest date matches the newest `trade_date` in prediction storage

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ml_factor_model_contract.py -k latest_prediction_date -v`
Expected: FAIL because the route does not exist yet.

**Step 3: Write minimal implementation**

Add a helper that reads `model_repo.get_predictions()`, normalizes `trade_date`, and returns the max date.
Add a new GET route `/scoring/latest-prediction-date` that uses that helper.

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_ml_factor_model_contract.py -k latest_prediction_date -v`
Expected: PASS

### Task 2: Make the scoring page switch date sources by mode

**Files:**
- Modify: `app/templates/ml_factor/scoring.html`
- Test: `tests/ui/test_scoring_template_contract.py`

**Step 1: Write the failing test**

Add a UI contract assertion that the template:
- calls the factor-date endpoint
- calls the prediction-date endpoint
- listens for scoring method changes

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_scoring_template_contract.py -v`
Expected: FAIL until the template contains the new ML date source logic.

**Step 3: Write minimal implementation**

On page load, load the factor date by default.
When the scoring method changes to ML mode, fetch and populate the latest prediction date.
When switching back to factor mode, fetch and populate the latest factor date.

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_scoring_template_contract.py -v`
Expected: PASS

### Task 3: Verify both scoring paths still work

**Files:**
- No code changes expected

**Step 1: Run targeted tests**

Run:
- `pytest tests/services/test_stock_scoring_parquet_integration.py -v`
- `pytest tests/api/test_ml_factor_model_contract.py -v`

Expected: PASS

**Step 2: Manual smoke check**

Open `/ml-factor/scoring`, switch between factor and ML modes, and confirm the date field updates to the newest available date for each mode.

