# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start the web server (only standard entry point)
python run.py

# Initialize DB and run diagnostics (not for daily use)
python run_system.py

# Run all tests
pytest

# Run a single test file
pytest tests/services/test_factor_engine_custom_factor_validation.py

# Run tests matching a keyword
pytest -k "portfolio"

# Install dependencies
pip install -r requirements.txt
# If empyrical or TA-Lib fail, fall back to:
pip install -r requirements_minimal.txt

# Celery worker (only needed when DATA_JOB_EXECUTION_MODE=celery)
celery -A app.celery_app.celery worker -l info -P solo
```

## Architecture

This is a **Flask + SQLAlchemy + SocketIO** quantitative stock analysis system (Chinese A-shares). The app factory is `app/__init__.py:create_app()`.

### Request Flow

```
HTTP → Blueprint (app/api/*.py) → Service (app/services/*.py) → SQLAlchemy models (app/models/*.py) → MySQL
WebSocket → app/websocket/websocket_events.py → app/services/websocket_push_service.py
```

HTML page routes live in `app/routes/` (separate from API blueprints).

### Key Services

| Service | File | Purpose |
|---|---|---|
| FactorEngine | `services/factor_engine.py` | Built-in & custom factor computation |
| FactorExpressionEngine | `services/factor_expression_engine.py` | Whitelist-validated custom factor formulas |
| MLModelManager | `services/ml_models.py` | XGBoost/LightGBM/RandomForest model lifecycle |
| ModelTrainingJobService | `services/model_training_job_service.py` | Async training job polling |
| StockScoringEngine | `services/stock_scoring.py` | Factor-based and ML-based scoring |
| PortfolioOptimizer | `services/portfolio_optimizer.py` | Equal-weight, mean-variance, risk-parity, factor-neutral |
| BacktestEngine | `services/backtest_engine.py` | Single-strategy and multi-strategy backtest |
| DataJobs | `services/data_jobs/` | Data download job runner (inline or Celery) |
| Text2SQL | `services/text2sql_engine.py` + `services/llm_service.py` | LLM-powered natural language to SQL |

### Blueprint URL Prefixes

- `/api` — main API (stock, analysis, text2sql)
- `/api/ml-factor/*` — factor management, ML models, scoring, portfolio optimization
- `/api/data-jobs/*` — data download job submission and status
- `/api/realtime-analysis/*` — realtime indicators, signals, monitor, risk, reports
- `/api/websocket/*` — WebSocket management endpoints

### Data Jobs Execution Modes

Controlled by `DATA_JOB_EXECUTION_MODE` env var:
- `inline` (default in development) — runs in the web process, no Celery needed
- `celery` (default in production) — requires a Celery worker with Redis broker

### Configuration

All config in `config.py` via env vars (`.env` file). Key vars:
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — MySQL connection (default db: `stock_cursor`)
- `REDIS_HOST`, `REDIS_PORT` — Redis for Celery and caching
- `FLASK_ENV` — `development` or `production`
- `DATA_JOB_EXECUTION_MODE` — `inline` or `celery`

LLM provider for Text2SQL defaults to local Ollama (`qwen2.5-coder`), configurable to OpenAI via `LLM_CONFIG` in `config.py`.

### Test Structure

Tests use a real Flask app fixture (no DB — tests mock at the service boundary). Heavy optional deps (xgboost, lightgbm, cvxpy, baostock, tushare) are stubbed in `tests/conftest.py` so tests run without installing them.

- `tests/services/` — service-layer unit/contract tests
- `tests/api/` — Flask test client API contract tests
- `tests/regression/` — regression guards against demo/mock data leaking into real paths
- `tests/ui/` — UI-level checks

### Data Download Utils

`app/utils/` contains standalone scripts for downloading market data from Tushare and Baostock. These can be run directly (`python app/utils/trade_calendar.py`) or triggered via the `/realtime-analysis` → Daily Data Center UI. Download order matters: `trade_calendar.py` → `stock_basic.py` → other scripts.

### Python Version

Supports Python 3.8–3.11. Python 3.12 has partial compatibility issues with some optional packages. The `runtime_compat.py` module patches `click.ParameterSource` for older Click versions.
