# Stock Detail Finance Tab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new `财务数据` tab to `/stock/<ts_code>` that shows the latest period of the balance sheet, income statement, and cash flow statement in three stacked sections.

**Architecture:** The backend will expose a dedicated financial-data endpoint for a single stock code, backed by the existing parquet reader. The service layer will normalize each statement to the latest reporting period, keep only the selected important fields, and return a UI-friendly payload with labels and values. The stock detail template will add one more tab and render three vertical blocks in a compact table layout, reusing the page's existing loading and formatting helpers.

**Tech Stack:** Flask, Jinja2, pandas, parquet-backed data reader, Bootstrap, vanilla JavaScript.

---

### Task 1: Add parquet reader support for cash flow data

**Files:**
- Modify: `app/services/data_reader.py`

**Step 1: Write the failing test**

Add a small regression test or a local verification script that imports `ParquetDataReader` and calls `get_cash_flow(["000001.SZ"])`, expecting a DataFrame object instead of `AttributeError`.

**Step 2: Run test to verify it fails**

Run: `python - <<'PY'
from app.services.data_reader import ParquetDataReader
reader = ParquetDataReader()
print(reader.get_cash_flow(["000001.SZ"]).head())
PY`

Expected: fail because `get_cash_flow` does not exist yet.

**Step 3: Write minimal implementation**

Add `cash_flow` to `TABLE_DIRS` and implement `get_cash_flow(self, ts_codes: List[str]) -> pd.DataFrame` using `_read_table("cash_flow", ts_codes, None, None)`, then sort by `ts_code` and `end_date` descending when present, matching the existing income statement and balance sheet behavior.

**Step 4: Run test to verify it passes**

Run the same Python snippet.

Expected: returns a DataFrame without raising.

---

### Task 2: Expose latest financial statements through the stock service and API

**Files:**
- Modify: `app/services/stock_service.py`
- Modify: `app/api/stock_api.py`

**Step 1: Write the failing test**

Add a focused API check that requests `GET /stocks/000001.SZ/financials` and expects a `200` response with keys for `balance_sheet`, `income_statement`, and `cash_flow`.

**Step 2: Run test to verify it fails**

Run: `pytest` or a direct Flask test client call against the new route.

Expected: 404 or missing route / missing method before the implementation exists.

**Step 3: Write minimal implementation**

In `StockService`, add a method that:
- fetches each statement via `_data_reader`
- filters to `ts_code`
- takes the latest `end_date` row for each table
- converts `NaN` to `None`
- formats `end_date` as a string
- returns a payload containing the three statements and their reporting dates

Add a matching API route, for example `@api_bp.route('/stocks/<ts_code>/financials')`, that wraps the service result in the same `{code, message, data}` envelope used elsewhere.

**Step 4: Run test to verify it passes**

Run the endpoint check again.

Expected: `200` with a structured JSON payload.

---

### Task 3: Render the financial-data tab in the stock detail page

**Files:**
- Modify: `app/templates/stock_detail.html`

**Step 1: Write the failing test**

Open `/stock/000001.SZ` locally and verify there is no `财务数据` tab and no finance content container yet.

**Step 2: Run test to verify it fails**

Run the app and inspect the page.

Expected: the new tab is absent.

**Step 3: Write minimal implementation**

Add a new `财务数据` nav item after `筹码分布`, a matching tab pane, and a `loadFinancialData()` JavaScript function that calls the new API endpoint and renders three stacked sections:
- 资产负债表
- 利润表
- 现金流量表

Each section should show only the latest period and use the user-selected fields with Chinese labels and consistent number formatting.

**Step 4: Run test to verify it passes**

Reload the page and click the new tab.

Expected: the tab loads, shows the three sections top-to-bottom, and no layout overflow or broken wrapping appears in the compact rows.

---

### Task 4: Verify the page and API against the target stock code

**Files:**
- Modify: none

**Step 1: Write the failing test**

Request the new financial endpoint and view the rendered tab for `000001.SZ`.

**Step 2: Run test to verify it fails**

Check that:
- the API returns non-empty data when the parquet files contain records
- the UI shows the latest period for each statement
- missing fields display as `--` instead of breaking the layout

**Step 3: Write minimal implementation**

If any field names or date formatting are off, adjust the backend payload and template helpers only as needed.

**Step 4: Run test to verify it passes**

Use the browser and one direct API request to confirm the final behavior.

**Step 5: Commit**

```bash
git add app/services/data_reader.py app/services/stock_service.py app/api/stock_api.py app/templates/stock_detail.html docs/plans/2026-06-04-stock-detail-finance-tab-implementation.md
git commit -m "feat: add stock finance data tab"
```
