# ML-Factor Parquet Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove MySQL as the default storage layer for the `/ml-factor` feature set by moving factor metadata, factor values, model metadata, predictions, portfolio state, and backtest records to Parquet-backed repositories.

**Architecture:** Keep `ParquetDataReader` as the read path for market data and introduce a dedicated Parquet state layer for `/ml-factor` business objects. The migration should be incremental: first define durable Parquet contracts and repositories, then swap each service/API to those repositories, and only at the end remove MySQL-specific persistence from the `/ml-factor` path. During the transition, preserve read compatibility so existing data can still be queried while the new Parquet stores are being populated.

**Tech Stack:** Python, Flask, pandas, PyArrow, pytest, SQLAlchemy-compatible models during transition, filesystem-backed Parquet storage

---

### Task 1: Define the Parquet state contracts for `/ml-factor`

**Files:**
- Create: `tests/services/test_parquet_state_store_contract.py`
- Create: `tests/services/test_factor_repository_contract.py`
- Create: `tests/services/test_model_repository_contract.py`
- Create: `tests/services/test_portfolio_repository_contract.py`
- Create: `tests/services/test_backtest_repository_contract.py`
- Create: `app/services/parquet_state_store.py`

**Step 1: Write the failing tests**

Add contract tests that assert:
- factor definitions can be created, listed, updated, and soft-deleted through a Parquet repository
- factor values can be overwritten by `(trade_date, factor_id)` and read back sorted by `ts_code`
- model definitions and predictions can be round-tripped by `model_id` and `trade_date`
- portfolio positions can be created, listed, deactivated, and reconstructed by `portfolio_id`
- backtest runs can be stored and retrieved by `run_id`

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/services/test_parquet_state_store_contract.py tests/services/test_factor_repository_contract.py tests/services/test_model_repository_contract.py tests/services/test_portfolio_repository_contract.py tests/services/test_backtest_repository_contract.py -v
```

Expected: FAIL because the Parquet state layer does not exist yet.

**Step 3: Write minimal implementation**

Implement a small Parquet state store abstraction that handles:
- directory layout per entity type
- append/overwrite semantics by business key
- read helpers for equality filters, `trade_date` ranges, and `portfolio_id`/`model_id` lookups
- consistent schema normalization for all `/ml-factor` entities

**Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/services/test_parquet_state_store_contract.py tests/services/test_factor_repository_contract.py tests/services/test_model_repository_contract.py tests/services/test_portfolio_repository_contract.py tests/services/test_backtest_repository_contract.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add app/services/parquet_state_store.py tests/services/test_parquet_state_store_contract.py tests/services/test_factor_repository_contract.py tests/services/test_model_repository_contract.py tests/services/test_portfolio_repository_contract.py tests/services/test_backtest_repository_contract.py
git commit -m "feat: define parquet state contracts for ml-factor"
```

### Task 2: Migrate factor metadata and factor values off MySQL

**Files:**
- Modify: `app/services/factor_engine.py`
- Modify: `app/api/ml_factor_api.py`
- Modify: `app/services/stock_scoring.py`
- Create: `tests/api/test_ml_factor_factor_contract.py`
- Create: `tests/services/test_factor_engine_parquet_integration.py`

**Step 1: Write the failing tests**

Add tests that assert:
- `/api/ml-factor/factors/custom`, `/api/ml-factor/factors/list`, and `/api/ml-factor/factors/calculate` use Parquet-backed factor storage
- factor values survive a save/read round-trip without touching `FactorValues.query`
- factor scoring reads the Parquet factor store and still returns the expected stock ranking payload

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/api/test_ml_factor_factor_contract.py tests/services/test_factor_engine_parquet_integration.py -v
```

Expected: FAIL because factor metadata and factor values still rely on ORM-backed persistence.

**Step 3: Write minimal implementation**

Replace the factor definition and factor value ORM calls with the new Parquet repository:
- load active definitions from Parquet on startup
- write factor values through the Parquet store using overwrite-by-key semantics
- update factor scoring reads to query Parquet directly
- keep temporary compatibility reads only where historical data must still be surfaced during migration

**Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/api/test_ml_factor_factor_contract.py tests/services/test_factor_engine_parquet_integration.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add app/services/factor_engine.py app/api/ml_factor_api.py app/services/stock_scoring.py tests/api/test_ml_factor_factor_contract.py tests/services/test_factor_engine_parquet_integration.py
git commit -m "feat: migrate ml-factor metadata to parquet"
```

### Task 3: Migrate model definitions and predictions off MySQL

**Files:**
- Modify: `app/services/ml_models.py`
- Modify: `app/api/ml_factor_api.py`
- Modify: `app/services/model_training_job_service.py`
- Create: `tests/api/test_ml_factor_model_contract.py`
- Create: `tests/services/test_ml_model_manager_parquet_integration.py`

**Step 1: Write the failing tests**

Add tests that assert:
- model definitions are created and listed from Parquet
- training reads factor inputs from the Parquet factor store
- predictions are written to and read from Parquet by `model_id` and `trade_date`
- deleting a model removes its Parquet metadata and associated prediction files or marks them inactive

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/api/test_ml_factor_model_contract.py tests/services/test_ml_model_manager_parquet_integration.py -v
```

Expected: FAIL because model definitions and predictions are still MySQL-backed.

**Step 3: Write minimal implementation**

Move model metadata and prediction persistence to the Parquet repository:
- create/update model definitions without `MLModelDefinition.query`
- read training data from the Parquet factor store
- persist predictions in a Parquet partition keyed by `model_id` and `trade_date`
- keep the training progress service unaware of the storage backend

**Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/api/test_ml_factor_model_contract.py tests/services/test_ml_model_manager_parquet_integration.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add app/services/ml_models.py app/api/ml_factor_api.py app/services/model_training_job_service.py tests/api/test_ml_factor_model_contract.py tests/services/test_ml_model_manager_parquet_integration.py
git commit -m "feat: migrate ml-factor model state to parquet"
```

### Task 4: Migrate portfolio and backtest state to Parquet

**Files:**
- Modify: `app/api/ml_factor_api.py`
- Modify: `app/services/backtest_engine.py`
- Modify: `app/models/portfolio_position.py`
- Modify: `app/models/backtest_run.py`
- Create: `tests/api/test_ml_factor_portfolio_contract.py`
- Create: `tests/api/test_ml_factor_backtest_contract.py`
- Create: `tests/services/test_backtest_engine_parquet_integration.py`

**Step 1: Write the failing tests**

Add tests that assert:
- portfolio list/detail/save/delete endpoints operate on Parquet-backed state
- backtest runs are persisted in Parquet and can be fetched by `run_id`
- backtest execution still returns the UI-shaped response while reading stock metadata from Parquet

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/api/test_ml_factor_portfolio_contract.py tests/api/test_ml_factor_backtest_contract.py tests/services/test_backtest_engine_parquet_integration.py -v
```

Expected: FAIL because portfolio and backtest state still depend on ORM tables.

**Step 3: Write minimal implementation**

Replace portfolio and backtest ORM persistence with Parquet-backed repositories:
- store each portfolio's active positions in Parquet partitions
- keep logical soft-delete semantics through an `is_active` field
- persist backtest run summaries and results to Parquet
- continue using Parquet market data for performance calculations

**Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/api/test_ml_factor_portfolio_contract.py tests/api/test_ml_factor_backtest_contract.py tests/services/test_backtest_engine_parquet_integration.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add app/api/ml_factor_api.py app/services/backtest_engine.py app/models/portfolio_position.py app/models/backtest_run.py tests/api/test_ml_factor_portfolio_contract.py tests/api/test_ml_factor_backtest_contract.py tests/services/test_backtest_engine_parquet_integration.py
git commit -m "feat: migrate ml-factor portfolio and backtest state to parquet"
```

### Task 5: Migrate analysis endpoints and UI assumptions to Parquet-backed data

**Files:**
- Modify: `app/api/ml_factor_api.py`
- Modify: `app/templates/ml_factor/analysis.html`
- Modify: `app/services/realtime_report_generator.py` if reused by the analysis page
- Create: `tests/api/test_ml_factor_analysis_contract.py`
- Create: `tests/ui/test_ml_factor_analysis_contract.py`

**Step 1: Write the failing tests**

Add tests that assert:
- the analysis endpoints return concrete payloads for model performance, factor effectiveness, portfolio performance, risk analysis, and report generation
- the frontend no longer expects missing endpoints or derives business metrics locally
- report generation uses Parquet-backed inputs rather than MySQL tables

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/api/test_ml_factor_analysis_contract.py tests/ui/test_ml_factor_analysis_contract.py -v
```

Expected: FAIL because the current analysis page has endpoint gaps and mixed backend assumptions.

**Step 3: Write minimal implementation**

Implement the missing analysis endpoints or wire them to existing Parquet-backed services:
- model performance summary
- factor effectiveness summary
- portfolio performance summary
- risk analysis summary
- report generation/export

Then update the UI to consume only backend-provided fields.

**Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/api/test_ml_factor_analysis_contract.py tests/ui/test_ml_factor_analysis_contract.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add app/api/ml_factor_api.py app/templates/ml_factor/analysis.html app/services/realtime_report_generator.py tests/api/test_ml_factor_analysis_contract.py tests/ui/test_ml_factor_analysis_contract.py
git commit -m "feat: align analysis ui with parquet-backed data"
```

### Task 6: Remove MySQL from the `/ml-factor` runtime path and finalize migration

**Files:**
- Modify: `config.py`
- Modify: `app/utils/db_utils.py`
- Modify: `README.md`
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`
- Modify: `app/__init__.py` if any `/ml-factor` bootstrap still assumes ORM storage
- Create: `tests/test_ml_factor_no_mysql_contract.py`

**Step 1: Write the failing test**

Add a contract test that scans `/ml-factor` services and asserts there are no remaining default persistence calls to:
- `FactorDefinition.query`
- `FactorValues.query`
- `MLModelDefinition.query`
- `MLPredictions.query`
- `PortfolioPosition.query`
- `BacktestRun.query`

Keep the test scoped to the `/ml-factor` path so unrelated legacy modules do not block the migration.

**Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_ml_factor_no_mysql_contract.py -v
```

Expected: FAIL because the migration is not fully complete yet.

**Step 3: Write minimal implementation**

Remove the remaining MySQL assumptions from the `/ml-factor` path:
- make Parquet the default data source in runtime config and docs
- keep MySQL only if some unrelated feature still needs it outside `/ml-factor`
- clean up compatibility shims that are no longer referenced

**Step 4: Run the test to verify it passes**

Run:

```bash
pytest tests/test_ml_factor_no_mysql_contract.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add config.py app/utils/db_utils.py README.md docker-compose.yml CLAUDE.md app/__init__.py tests/test_ml_factor_no_mysql_contract.py
git commit -m "feat: remove mysql defaults from ml-factor"
```

### Task 7: Run the end-to-end migration verification

**Files:**
- Verify only

**Step 1: Run the focused contract suite**

Run:

```bash
pytest tests/services/test_parquet_state_store_contract.py tests/services/test_factor_repository_contract.py tests/services/test_model_repository_contract.py tests/services/test_portfolio_repository_contract.py tests/services/test_backtest_repository_contract.py tests/api/test_ml_factor_factor_contract.py tests/api/test_ml_factor_model_contract.py tests/api/test_ml_factor_portfolio_contract.py tests/api/test_ml_factor_backtest_contract.py tests/api/test_ml_factor_analysis_contract.py tests/test_ml_factor_no_mysql_contract.py -v
```

Expected: PASS

**Step 2: Run a syntax and import smoke test**

Run:

```bash
python -m py_compile app/services/parquet_state_store.py app/services/factor_engine.py app/services/ml_models.py app/services/stock_scoring.py app/services/backtest_engine.py app/api/ml_factor_api.py
```

Expected: no output

**Step 3: Run a manual UI smoke check**

Open:

```text
http://localhost:5000/ml-factor/
http://localhost:5000/ml-factor/models
http://localhost:5000/ml-factor/scoring
http://localhost:5000/ml-factor/portfolio
http://localhost:5000/ml-factor/backtest
http://localhost:5000/ml-factor/analysis
```

Expected: pages load and all visible actions complete without MySQL-backed errors.

