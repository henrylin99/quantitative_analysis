# Frontend Theme Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the shared frontend theme and ML factor pages so buttons, typography, spacing, and dark-mode contrast feel polished and readable.

**Architecture:** Keep Bootstrap 5 and the existing Flask/Jinja template structure. Add conservative shared CSS overrides in `base.html` and `financial-theme.css`, then use small page-level class hooks in the scoring and portfolio templates for denser ML workflows.

**Tech Stack:** Flask, Jinja2 templates, Bootstrap 5.1.3, Font Awesome, vanilla JavaScript, CSS, Playwright or browser screenshots for visual verification.

---

### Task 1: Capture Current Visual Baseline

**Files:**
- Read: `app/templates/base.html`
- Read: `app/static/css/financial-theme.css`
- Read: `app/static/css/responsive-financial.css`
- Read: `app/templates/ml_factor/scoring.html`
- Read: `app/templates/ml_factor/portfolio.html`

**Step 1: Confirm the app start command**

Run:

```bash
rg -n "flask|run.py|run_system|python run" README.md CLAUDE.md run.py run_system.py
```

Expected: output shows the local development command or Flask entry point.

**Step 2: Start the app locally**

Use the repo's documented command. If no command is documented, try:

```bash
python run.py
```

Expected: local Flask app starts and prints a URL or binds a localhost port.

**Step 3: Capture baseline screenshots**

Use Playwright or a browser to capture:

- `/ml-factor/scoring`
- `/ml-factor/portfolio`

Capture both light and dark color schemes if Playwright is available:

```js
await page.emulateMedia({ colorScheme: 'light' });
await page.goto('http://127.0.0.1:<port>/ml-factor/scoring');
await page.screenshot({ path: 'tmp/scoring-light-before.png', fullPage: true });
await page.emulateMedia({ colorScheme: 'dark' });
await page.screenshot({ path: 'tmp/scoring-dark-before.png', fullPage: true });
```

Expected: screenshots show current oversized controls and weak dark-mode contrast.

**Step 4: Commit**

Do not commit screenshots unless the repo already tracks visual regression assets. Keep screenshots in `tmp/` or another ignored local path.

---

### Task 2: Add Theme Tokens And Global Density Overrides

**Files:**
- Modify: `app/static/css/financial-theme.css`

**Step 1: Add light and dark surface tokens**

In `:root`, add tokens after the existing neutral colors:

```css
    --app-bg: #f6f8fb;
    --surface-bg: #ffffff;
    --surface-bg-subtle: #f8fafc;
    --surface-border: #d9e0ea;
    --text-primary: #172033;
    --text-secondary: #4b5870;
    --text-muted: #69758a;
    --control-bg: #ffffff;
    --control-border: #cbd5e1;
    --control-placeholder: #8a95a8;
    --table-hover-bg: #eef4fb;
```

Then add a complete dark-mode token block near the end of the file, before responsive rules:

```css
@media (prefers-color-scheme: dark) {
    :root {
        --app-bg: #111827;
        --surface-bg: #1f2937;
        --surface-bg-subtle: #263244;
        --surface-border: #435168;
        --text-primary: #f3f7fb;
        --text-secondary: #d2d9e5;
        --text-muted: #aab5c6;
        --control-bg: #172033;
        --control-border: #526179;
        --control-placeholder: #9aa7ba;
        --table-hover-bg: #2a374a;
    }
}
```

**Step 2: Update base typography**

Change `body` to use the new tokens and reduce the default scale:

```css
body {
    font-family: var(--font-family);
    font-size: 0.875rem;
    line-height: 1.55;
    color: var(--text-primary);
    background-color: var(--app-bg);
}

h1,
.h1 {
    font-size: clamp(1.5rem, 2vw, 1.75rem);
    font-weight: 600;
    letter-spacing: 0;
}

h5,
.h5 {
    font-size: 0.98rem;
    font-weight: 600;
}

.text-muted {
    color: var(--text-muted) !important;
}
```

**Step 3: Update cards and financial cards**

Change `.card-financial` and add shared Bootstrap card overrides:

```css
.card,
.card-financial {
    background: var(--surface-bg);
    border-color: var(--surface-border);
    color: var(--text-primary);
    border-radius: var(--border-radius);
    box-shadow: var(--shadow-sm);
}

.card-header {
    background: var(--surface-bg-subtle);
    border-bottom-color: var(--surface-border);
    color: var(--text-primary);
    padding: 0.65rem 0.9rem;
}

.card-body {
    padding: 0.9rem;
}
```

Keep existing `.card-financial:hover`, but reduce movement:

```css
.card-financial:hover {
    box-shadow: var(--shadow);
    transform: translateY(-1px);
}
```

**Step 4: Run CSS grep check**

Run:

```bash
rg -n "font-size: 2rem|font-weight: 700|translateY\\(-4px\\)|#2d3748|#e2e8f0" app/static/css/financial-theme.css app/templates/base.html
```

Expected: remaining matches are either intentional icon sizing or legacy `base.html` dark-mode rules to remove in a later task.

**Step 5: Commit**

```bash
git add app/static/css/financial-theme.css
git commit -m "style: add compact theme tokens"
```

---

### Task 3: Normalize Buttons, Forms, Tables, Dropdowns, And Modals

**Files:**
- Modify: `app/static/css/financial-theme.css`

**Step 1: Add compact button overrides**

Add after the existing financial button block:

```css
.btn {
    --bs-btn-font-size: 0.875rem;
    --bs-btn-font-weight: 500;
    --bs-btn-padding-x: 0.78rem;
    --bs-btn-padding-y: 0.36rem;
    border-radius: var(--border-radius-sm);
    line-height: 1.35;
}

.btn-sm {
    --bs-btn-font-size: 0.78rem;
    --bs-btn-padding-x: 0.5rem;
    --bs-btn-padding-y: 0.24rem;
}

.btn i {
    font-size: 0.92em;
}

.btn-financial {
    font-weight: 500;
    padding: 0.42rem 0.85rem;
    border-radius: var(--border-radius-sm);
}
```

Reduce hover motion in `.btn-primary-financial:hover`, `.btn-success-financial:hover`, `.btn-warning-financial:hover`, and `.btn-danger-financial:hover` to `translateY(-1px)`.

**Step 2: Add form control overrides**

```css
.form-label {
    color: var(--text-secondary);
    font-size: 0.82rem;
    font-weight: 500;
    margin-bottom: 0.35rem;
}

.form-control,
.form-select {
    background-color: var(--control-bg);
    border-color: var(--control-border);
    color: var(--text-primary);
    font-size: 0.875rem;
    min-height: 2.1rem;
    padding: 0.35rem 0.6rem;
}

.form-control::placeholder {
    color: var(--control-placeholder);
}

.form-text {
    color: var(--text-muted);
    font-size: 0.78rem;
}
```

**Step 3: Add table overrides**

```css
.table {
    color: var(--text-primary);
    font-size: 0.84rem;
    margin-bottom: 0;
}

.table > :not(caption) > * > * {
    background-color: transparent;
    border-bottom-color: var(--surface-border);
    padding: 0.5rem 0.6rem;
}

.table thead th,
.table-financial thead th {
    background: var(--surface-bg-subtle);
    color: var(--text-secondary);
    font-size: 0.78rem;
    font-weight: 600;
    padding: 0.5rem 0.6rem;
}

.table-hover > tbody > tr:hover > * {
    background-color: var(--table-hover-bg);
    color: var(--text-primary);
}
```

Remove or override `.table-financial tbody tr:hover { transform: scale(1.01); }` with `transform: none;`.

**Step 4: Add dropdown and modal overrides**

```css
.dropdown-menu,
.modal-content {
    background-color: var(--surface-bg);
    border-color: var(--surface-border);
    color: var(--text-primary);
}

.dropdown-item {
    color: var(--text-primary);
    font-size: 0.875rem;
}

.dropdown-item:hover,
.dropdown-item:focus {
    background-color: var(--surface-bg-subtle);
    color: var(--primary-light);
}

.modal-header,
.modal-footer {
    border-color: var(--surface-border);
}
```

**Step 5: Run syntax and grep checks**

Run:

```bash
rg -n "transform: scale\\(1.01\\)|translateY\\(-2px\\)|font-weight: 700" app/static/css/financial-theme.css
```

Expected: no table scale transform remains; any `font-weight: 700` is intentional for metrics only.

**Step 6: Commit**

```bash
git add app/static/css/financial-theme.css
git commit -m "style: compact shared controls"
```

---

### Task 4: Replace Partial Dark Mode Rules In Base Template

**Files:**
- Modify: `app/templates/base.html`

**Step 1: Remove conflicting inline dark-mode card/table block**

In the `<style>` block, remove the existing partial dark-mode section:

```css
        /* 深色模式支持 */
        @media (prefers-color-scheme: dark) {
            .card {
                background-color: #2d3748;
                border-color: #4a5568;
                color: #e2e8f0;
            }
            
            .table {
                color: #e2e8f0;
            }
            
            .table-striped > tbody > tr:nth-of-type(odd) > td {
                background-color: rgba(255, 255, 255, 0.05);
            }
        }
```

Shared dark-mode tokens in `financial-theme.css` now own this behavior.

**Step 2: Make navbar brand less heavy**

Change:

```css
.navbar-brand {
    font-weight: bold;
}
```

To:

```css
.navbar-brand {
    font-weight: 600;
}
```

**Step 3: Reduce mobile button padding only where needed**

Keep iOS touch targets but avoid oversized mobile buttons. Confirm mobile `.btn` rules remain no larger than:

```css
.btn {
    padding: 0.4rem 0.75rem;
    font-size: 0.84rem;
}
```

**Step 4: Run template grep check**

Run:

```bash
rg -n "#2d3748|#e2e8f0|font-weight: bold|prefers-color-scheme: dark" app/templates/base.html
```

Expected: no old partial dark-mode block remains in `base.html`.

**Step 5: Commit**

```bash
git add app/templates/base.html
git commit -m "style: remove conflicting inline dark mode"
```

---

### Task 5: Add ML Factor Page Density Hooks

**Files:**
- Modify: `app/static/css/financial-theme.css`
- Modify: `app/templates/ml_factor/scoring.html`
- Modify: `app/templates/ml_factor/portfolio.html`

**Step 1: Add ML factor CSS hooks**

In `financial-theme.css`, add:

```css
.ml-factor-page {
    padding-bottom: 1.5rem;
}

.ml-factor-page .page-heading {
    margin-bottom: 1rem;
}

.ml-factor-page .page-heading h1 {
    margin-bottom: 0.25rem;
}

.ml-factor-page .page-heading .page-icon {
    font-size: 0.9em;
    margin-right: 0.35rem;
}

.ml-factor-page .config-card .row {
    row-gap: 0.75rem;
}

.ml-factor-page .config-card .card-body {
    padding: 0.85rem;
}

.ml-factor-page .table .btn-sm {
    min-width: 1.85rem;
}

.ml-factor-page code {
    color: var(--primary-light);
    background-color: var(--surface-bg-subtle);
    border: 1px solid var(--surface-border);
    border-radius: 0.25rem;
    padding: 0.08rem 0.25rem;
}
```

**Step 2: Update scoring page wrapper and config card**

Change the outer container:

```html
<div class="container">
```

To:

```html
<div class="container ml-factor-page">
```

Change the heading:

```html
<div class="row mb-4">
```

To:

```html
<div class="row page-heading">
```

Change:

```html
<h1>⭐ 股票评分</h1>
```

To:

```html
<h1><span class="page-icon">⭐</span>股票评分</h1>
```

Add `config-card` to the scoring config card:

```html
<div class="card config-card">
```

**Step 3: Update portfolio page wrapper and config card**

Apply the same outer wrapper and heading changes:

```html
<div class="container ml-factor-page">
```

```html
<div class="row page-heading">
```

```html
<h1><span class="page-icon">💼</span>投资组合</h1>
```

Add `config-card` to the portfolio optimization card:

```html
<div class="card config-card">
```

**Step 4: Verify generated action buttons remain functional**

Do not change JavaScript function names or endpoint calls. Confirm these still exist:

```bash
rg -n "calculateScoring|optimizePortfolio|createPortfolio|viewPortfolioDetail|openPositionModal" app/templates/ml_factor/scoring.html app/templates/ml_factor/portfolio.html
```

Expected: all existing functions still appear.

**Step 5: Commit**

```bash
git add app/static/css/financial-theme.css app/templates/ml_factor/scoring.html app/templates/ml_factor/portfolio.html
git commit -m "style: tighten ml factor pages"
```

---

### Task 6: Visual Verification

**Files:**
- Verify: `app/static/css/financial-theme.css`
- Verify: `app/templates/base.html`
- Verify: `app/templates/ml_factor/scoring.html`
- Verify: `app/templates/ml_factor/portfolio.html`

**Step 1: Start or reuse the local app server**

Run the documented command from Task 1.

Expected: app serves locally without template errors.

**Step 2: Check light mode**

Open:

- `/ml-factor/scoring`
- `/ml-factor/portfolio`

Expected:

- Buttons look smaller and less heavy.
- Page titles and card headers are compact.
- Tables remain readable.
- Form controls align cleanly.
- Modals still open and have readable text.

**Step 3: Check dark mode with Playwright**

Use:

```js
await page.emulateMedia({ colorScheme: 'dark' });
```

Expected:

- Body, cards, inputs, dropdowns, modals, tables, alerts, and `.text-muted` are readable.
- No dark surface uses near-identical text and background colors.

**Step 4: Run automated smoke checks if available**

Run:

```bash
pytest -q
```

If the full suite is too slow or requires unavailable services, run the smallest relevant suite and record what could not run.

Expected: tests pass or unrelated environment failures are documented.

**Step 5: Commit verification fixes**

If visual checks reveal small CSS regressions, fix them and commit:

```bash
git add app/static/css/financial-theme.css app/templates/base.html app/templates/ml_factor/scoring.html app/templates/ml_factor/portfolio.html
git commit -m "style: polish theme verification issues"
```

---

### Task 7: Final Review

**Files:**
- Review: `app/static/css/financial-theme.css`
- Review: `app/templates/base.html`
- Review: `app/templates/ml_factor/scoring.html`
- Review: `app/templates/ml_factor/portfolio.html`

**Step 1: Check final diff**

Run:

```bash
git diff HEAD~4..HEAD -- app/static/css/financial-theme.css app/templates/base.html app/templates/ml_factor/scoring.html app/templates/ml_factor/portfolio.html
```

Expected: only presentation-related changes.

**Step 2: Check worktree status**

Run:

```bash
git status --short
```

Expected: clean or only intentionally untracked local screenshots in ignored paths.

**Step 3: Summarize verification**

Record:

- Pages checked.
- Light/dark mode status.
- Tests run.
- Any residual visual risk.

**Step 4: Commit plan document if not already committed**

```bash
git add -f docs/plans/2026-06-04-frontend-theme-redesign-implementation.md
git commit -m "docs: add frontend theme redesign plan"
```
