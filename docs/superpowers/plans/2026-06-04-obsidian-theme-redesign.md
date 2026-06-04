# Obsidian Theme Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the entire Flask/Jinja2 quantitative analysis frontend into an Obsidian dark theme with Indigo accents, DM Sans typography, and restrained micro-animations.

**Architecture:** Keep Bootstrap 5 and Jinja2 template inheritance. Replace `financial-theme.css` entirely with Obsidian tokens. Update `base.html` navbar and inline styles. Modify 24 page templates to remove emoji headings and light-theme inline styles. Convert standalone `text2sql/index.html` to extend `base.html`. Delete dead `mobile.css`. Override Bootstrap utility classes globally.

**Tech Stack:** Flask, Jinja2, Bootstrap 5.1.3, Font Awesome, ECharts 5.4.3, Google Fonts (DM Sans), CSS custom properties.

**Spec:** `docs/superpowers/specs/2026-06-04-obsidian-theme-redesign.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/static/css/financial-theme.css` | Rewrite | Obsidian design tokens + all component styles + Bootstrap utility overrides |
| `app/static/css/responsive-financial.css` | Modify | Replace light-theme colors with Obsidian tokens |
| `app/static/css/mobile.css` | Delete | Dead code — not loaded by any template |
| `app/templates/base.html` | Modify | Navbar redesign, font import, ECharts theme, inline styles |
| `app/templates/index.html` | Modify | Remove emoji, remove light-theme inline styles |
| `app/templates/analysis.html` | Modify | Remove emoji, remove purple gradient inline styles |
| `app/templates/stocks.html` | Modify | Remove emoji if any |
| `app/templates/screen.html` | Modify | Remove emoji if any |
| `app/templates/backtest.html` | Modify | Remove emoji, remove light-theme inline styles |
| `app/templates/stock_detail.html` | Modify | Remove emoji, remove light-theme inline styles |
| `app/templates/text2sql/index.html` | Rewrite | Convert to extend base.html, remove standalone styles |
| `app/templates/ml_factor/index.html` | Modify | Remove emoji from heading |
| `app/templates/ml_factor/analysis.html` | Modify | Remove emoji from heading |
| `app/templates/ml_factor/backtest.html` | Modify | Remove emoji from heading |
| `app/templates/ml_factor/models.html` | Modify | Remove emoji from heading |
| `app/templates/ml_factor/portfolio.html` | Modify | Remove emoji from heading |
| `app/templates/ml_factor/scoring.html` | Modify | Remove emoji from heading |
| `app/templates/realtime_analysis/index.html` | Modify | Remove emoji if any |
| `app/templates/realtime_analysis/indicators.html` | Modify | Remove light-theme inline styles |
| `app/templates/realtime_analysis/monitor.html` | Modify | Remove light-theme inline styles |
| `app/templates/realtime_analysis/report_management.html` | Modify | Remove light-theme inline styles |
| `app/templates/realtime_analysis/risk_management.html` | Modify | Remove light-theme inline styles |
| `app/templates/realtime_analysis/signals.html` | Modify | Remove light-theme inline styles |
| `app/templates/realtime_analysis/websocket_management.html` | Modify | Remove light-theme inline styles |
| `app/templates/data_management/index.html` | Modify | Remove purple gradient inline styles, status colors |

---

### Task 1: Rewrite financial-theme.css with Obsidian Tokens

**Files:**
- Rewrite: `app/static/css/financial-theme.css`

This is the foundation — all other tasks depend on this being correct.

- [ ] **Step 1: Replace `:root` variables with Obsidian tokens**

Replace the entire `:root` block with:

```css
:root {
    /* Surfaces */
    --obs-bg: #0f172a;
    --obs-surface: #1e293b;
    --obs-surface-alt: #162033;
    --obs-border: #334155;
    --obs-border-light: rgba(99,102,241,0.15);
    --obs-border-hover: rgba(99,102,241,0.3);

    /* Text */
    --obs-text: #e2e8f0;
    --obs-text-secondary: #94a3b8;
    --obs-text-muted: #64748b;

    /* Brand */
    --obs-primary: #6366f1;
    --obs-primary-light: #818cf8;
    --obs-primary-bg: rgba(99,102,241,0.10);
    --obs-primary-glow: rgba(99,102,241,0.25);

    /* Semantic */
    --obs-success: #22c55e;
    --obs-success-light: #4ade80;
    --obs-success-bg: rgba(34,197,94,0.10);
    --obs-warning: #f59e0b;
    --obs-warning-light: #fbbf24;
    --obs-warning-bg: rgba(245,158,11,0.10);
    --obs-danger: #ef4444;
    --obs-danger-light: #f87171;
    --obs-danger-bg: rgba(239,68,68,0.10);
    --obs-info: #06b6d4;
    --obs-info-light: #22d3ee;
    --obs-info-bg: rgba(6,182,212,0.10);

    /* Legacy aliases (for existing var() references) */
    --primary-color: #6366f1;
    --primary-light: #818cf8;
    --primary-dark: #4f46e5;
    --success-color: #22c55e;
    --warning-color: #f59e0b;
    --danger-color: #ef4444;
    --info-color: #06b6d4;
    --gray-50: #0f172a;
    --gray-100: #162033;
    --gray-200: #1e293b;
    --gray-300: #334155;
    --gray-400: #475569;
    --gray-500: #64748b;
    --gray-600: #94a3b8;
    --gray-700: #cbd5e1;
    --gray-800: #e2e8f0;
    --gray-900: #f1f5f9;

    /* Typography */
    --font-family: 'DM Sans', "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    --font-size-xs: 0.75rem;
    --font-size-sm: 0.8125rem;
    --font-size-base: 0.875rem;
    --font-size-lg: 1rem;
    --font-size-xl: 1.125rem;
    --font-size-2xl: 1.5rem;
    --font-size-3xl: 1.875rem;

    /* Spacing */
    --spacing-1: 0.25rem;
    --spacing-2: 0.5rem;
    --spacing-3: 0.75rem;
    --spacing-4: 1rem;
    --spacing-5: 1.25rem;
    --spacing-6: 1.5rem;
    --spacing-8: 2rem;

    /* Radius */
    --border-radius-sm: 0.375rem;
    --border-radius: 0.5rem;
    --border-radius-lg: 0.75rem;
    --border-radius-xl: 1rem;

    /* Shadows */
    --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);
    --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px 0 rgba(0, 0, 0, 0.3);
    --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -1px rgba(0, 0, 0, 0.3);

    /* Transitions */
    --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
    --transition-normal: 250ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

- [ ] **Step 2: Rewrite body and base styles**

```css
* { box-sizing: border-box; }

body {
    font-family: var(--font-family);
    font-size: var(--font-size-base);
    line-height: 1.55;
    color: var(--obs-text);
    background-color: var(--obs-bg);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

h1, .h1 { font-size: clamp(1.5rem, 2vw, 1.75rem); font-weight: 600; }
h5, .h5 { font-size: 0.98rem; font-weight: 600; }

.text-muted { color: var(--obs-text-muted) !important; }
```

- [ ] **Step 3: Rewrite navbar styles**

Replace all `.navbar-financial` styles:

```css
.navbar-financial {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--obs-border-light);
}

.navbar-financial .navbar-brand {
    font-weight: 600;
    font-size: var(--font-size-lg);
    color: white !important;
    transition: var(--transition-fast);
}

.navbar-financial .navbar-brand:hover {
    color: white !important;
}

.navbar-financial .nav-link {
    color: rgba(255, 255, 255, 0.7) !important;
    font-weight: 500;
    font-size: var(--font-size-sm);
    padding: var(--spacing-2) var(--spacing-3);
    border-radius: var(--border-radius);
    transition: var(--transition-fast);
}

.navbar-financial .nav-link:hover,
.navbar-financial .nav-link.active {
    color: var(--obs-primary-light) !important;
    background-color: rgba(99, 102, 241, 0.12);
}

.navbar-financial .dropdown-menu {
    background-color: var(--obs-surface);
    border: 1px solid var(--obs-border);
    box-shadow: var(--shadow-md);
    border-radius: var(--border-radius-lg);
    padding: var(--spacing-1);
    margin-top: var(--spacing-2);
}

.navbar-financial .dropdown-item {
    color: var(--obs-text);
    padding: var(--spacing-2) var(--spacing-3);
    border-radius: var(--border-radius-sm);
    transition: var(--transition-fast);
    font-weight: 500;
    font-size: var(--font-size-sm);
}

.navbar-financial .dropdown-item:hover {
    background-color: var(--obs-primary-bg);
    color: var(--obs-primary-light);
}
```

- [ ] **Step 4: Rewrite real-time indicator**

```css
.real-time-indicator {
    background: rgba(34, 197, 94, 0.15);
    color: var(--obs-success-light);
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.real-time-indicator::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    background: var(--obs-success-light);
    border-radius: 50%;
    margin-right: 4px;
}

/* Remove the old shimmer animation */
.real-time-indicator::after { display: none; }
```

- [ ] **Step 5: Rewrite card system**

```css
.card,
.card-financial {
    background: var(--obs-surface);
    border: 1px solid var(--obs-border);
    border-radius: var(--border-radius-lg);
    box-shadow: none;
    color: var(--obs-text);
    transition: var(--transition-normal);
}

.card:hover,
.card-financial:hover {
    border-color: var(--obs-border-hover);
    box-shadow: 0 0 20px rgba(99, 102, 241, 0.06);
}

.card-header {
    background: var(--obs-surface-alt);
    border-bottom: 1px solid var(--obs-border);
    color: var(--obs-text);
    padding: 0.65rem 0.9rem;
}

.card-body {
    padding: 0.9rem;
    color: var(--obs-text);
}

/* Metric card enhanced */
.metric-card-enhanced {
    background: var(--obs-surface);
    border: 1px solid var(--obs-border);
    border-radius: var(--border-radius-lg);
    transition: var(--transition-normal);
    overflow: hidden;
    position: relative;
}

.metric-card-enhanced::before {
    display: none; /* Remove old gradient top bar */
}

.metric-card-enhanced:hover {
    border-color: var(--obs-border-hover);
    box-shadow: 0 0 20px rgba(99, 102, 241, 0.06);
}

.metric-icon {
    width: 36px;
    height: 36px;
    margin: 0 auto var(--spacing-3);
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--obs-primary-bg);
    border-radius: var(--border-radius);
    transition: var(--transition-fast);
}

.metric-icon i {
    font-size: 1rem;
    transition: var(--transition-fast);
}

.metric-card-enhanced:hover .metric-icon {
    transform: none;
    background: var(--obs-primary-bg);
}

.metric-card-enhanced:hover .metric-icon i {
    color: var(--obs-primary-light) !important;
}
```

- [ ] **Step 6: Rewrite hero banner**

```css
.stock-info-banner {
    background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.05));
    color: var(--obs-text);
    border: 1px solid var(--obs-border-light);
    box-shadow: none;
    position: relative;
    overflow: hidden;
}

.stock-info-banner::before {
    content: '';
    position: absolute;
    top: 0;
    left: 10%;
    right: 10%;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(99,102,241,0.4), transparent);
}

.stock-info-banner .card-body {
    padding: var(--spacing-8) var(--spacing-6);
}

.stock-info-banner .display-4 {
    font-weight: 700;
    color: var(--obs-text);
}

.stock-info-banner .lead {
    color: var(--obs-primary-light);
}
```

- [ ] **Step 7: Rewrite button system**

```css
.btn-financial {
    font-weight: 500;
    font-size: var(--font-size-sm);
    padding: 6px 16px;
    border-radius: var(--border-radius);
    transition: var(--transition-fast);
    position: relative;
    overflow: hidden;
}

.btn-financial::before {
    display: none; /* Remove old shimmer sweep */
}

.btn-primary-financial {
    background: var(--obs-primary);
    border: none;
    color: white;
}

.btn-primary-financial:hover {
    background: var(--obs-primary-light);
    box-shadow: 0 0 16px var(--obs-primary-glow);
    color: white;
}

.btn-success-financial {
    background: var(--obs-success);
    border: none;
    color: white;
}

.btn-success-financial:hover {
    background: var(--obs-success-light);
    box-shadow: 0 0 16px rgba(34, 197, 94, 0.2);
    color: white;
}

.btn-warning-financial {
    background: var(--obs-warning);
    border: none;
    color: white;
}

.btn-warning-financial:hover {
    background: var(--obs-warning-light);
    box-shadow: 0 0 16px rgba(245, 158, 11, 0.2);
    color: white;
}

.btn-danger-financial {
    background: var(--obs-danger);
    border: none;
    color: white;
}

.btn-danger-financial:hover {
    background: var(--obs-danger-light);
    box-shadow: 0 0 16px rgba(239, 68, 68, 0.2);
    color: white;
}

/* Ghost/outline buttons */
.btn-outline-light {
    border-color: rgba(99, 102, 241, 0.3);
    color: var(--obs-primary-light);
}

.btn-outline-light:hover {
    background: var(--obs-primary-bg);
    border-color: var(--obs-primary);
    color: var(--obs-primary-light);
}

/* Hover-lift override - no lift */
.hover-lift { transition: var(--transition-normal); }
.hover-lift:hover {
    transform: none;
    box-shadow: 0 0 20px rgba(99, 102, 241, 0.06);
}

/* Metric card hover - no lift */
.metric-card { transition: var(--transition-fast); }
.metric-card:hover { transform: none; }
```

- [ ] **Step 8: Rewrite table styles**

```css
.table,
.table-financial {
    color: var(--obs-text);
    background: transparent;
    font-size: var(--font-size-sm);
    margin-bottom: 0;
}

.table > :not(caption) > * > * {
    background-color: transparent;
    border-bottom-color: rgba(51, 65, 85, 0.5);
    padding: 0.5rem 0.6rem;
}

.table thead th,
.table-financial thead th {
    background: var(--obs-surface-alt);
    color: var(--obs-text-muted);
    font-size: 12px;
    font-weight: 600;
    padding: 0.5rem 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border: none;
}

.table-financial tbody tr {
    transition: var(--transition-fast);
    transform: none !important;
}

.table-financial tbody tr:hover,
.table-hover > tbody > tr:hover > * {
    background-color: rgba(99, 102, 241, 0.06);
    color: var(--obs-text);
}

.table-striped > tbody > tr:nth-of-type(odd) > * {
    background-color: rgba(255, 255, 255, 0.02);
}
```

- [ ] **Step 9: Rewrite form styles**

```css
.form-control,
.form-select {
    background-color: var(--obs-surface-alt);
    border-color: var(--obs-border);
    color: var(--obs-text);
    font-size: var(--font-size-sm);
    min-height: 2.1rem;
    padding: 0.35rem 0.6rem;
    transition: var(--transition-fast);
}

.form-control:focus,
.form-select:focus {
    background-color: var(--obs-surface-alt);
    border-color: rgba(99, 102, 241, 0.5);
    color: var(--obs-text);
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.form-control::placeholder {
    color: var(--obs-text-muted);
}

.form-label {
    color: var(--obs-text-secondary);
    font-size: 12px;
    font-weight: 500;
    margin-bottom: 0.35rem;
}

.form-text {
    color: var(--obs-text-muted);
    font-size: var(--font-size-xs);
}
```

- [ ] **Step 10: Rewrite dropdown, modal, alert, badge styles**

```css
/* Dropdowns */
.dropdown-menu {
    background-color: var(--obs-surface);
    border: 1px solid var(--obs-border);
    border-radius: var(--border-radius-lg);
    box-shadow: var(--shadow-md);
}

.dropdown-item {
    color: var(--obs-text);
    font-size: var(--font-size-sm);
}

.dropdown-item:hover,
.dropdown-item:focus {
    background-color: var(--obs-primary-bg);
    color: var(--obs-primary-light);
}

/* Modals */
.modal-content {
    background-color: var(--obs-surface);
    border: 1px solid var(--obs-border);
    color: var(--obs-text);
}

.modal-header {
    border-bottom: 1px solid var(--obs-border);
}

.modal-footer {
    border-top: 1px solid var(--obs-border);
}

.btn-close {
    filter: invert(1) grayscale(100%) brightness(200%);
}

/* Alerts */
.alert { border: none; border-radius: var(--border-radius); padding: 0.75rem 1rem; }

.alert-danger-financial,
.alert-danger {
    background: var(--obs-danger-bg);
    border-left: 3px solid var(--obs-danger);
    color: var(--obs-danger-light);
}

.alert-success-financial,
.alert-success {
    background: var(--obs-success-bg);
    border-left: 3px solid var(--obs-success);
    color: var(--obs-success-light);
}

.alert-warning-financial,
.alert-warning {
    background: var(--obs-warning-bg);
    border-left: 3px solid var(--obs-warning);
    color: var(--obs-warning-light);
}

.alert-info-financial,
.alert-info {
    background: var(--obs-info-bg);
    border-left: 3px solid var(--obs-info);
    color: var(--obs-info-light);
}

/* Badges */
.badge {
    border-radius: 10px;
    font-size: 11px;
    font-weight: 500;
    padding: 2px 8px;
}

/* Nav tabs / pills */
.nav-tabs { border-bottom-color: var(--obs-border); }
.nav-tabs .nav-link {
    color: var(--obs-text-secondary);
    border-color: transparent;
}
.nav-tabs .nav-link.active {
    color: var(--obs-primary-light);
    background-color: var(--obs-surface);
    border-color: var(--obs-border) var(--obs-border) var(--obs-surface);
}
.nav-tabs .nav-link:hover {
    color: var(--obs-text);
    border-color: transparent;
}

.nav-pills .nav-link {
    color: var(--obs-text-secondary);
    border-radius: var(--border-radius);
}
.nav-pills .nav-link.active {
    background-color: var(--obs-primary-bg);
    color: var(--obs-primary-light);
}

/* Pagination */
.page-link {
    background-color: var(--obs-surface);
    border-color: var(--obs-border);
    color: var(--obs-text-secondary);
}
.page-link:hover {
    background-color: var(--obs-primary-bg);
    border-color: var(--obs-border);
    color: var(--obs-primary-light);
}
.page-item.active .page-link {
    background-color: var(--obs-primary);
    border-color: var(--obs-primary);
    color: white;
}

/* List group */
.list-group-item {
    background-color: var(--obs-surface);
    border-color: var(--obs-border);
    color: var(--obs-text);
}
.list-group-item-action:hover {
    background-color: var(--obs-primary-bg);
    color: var(--obs-primary-light);
}
```

- [ ] **Step 11: Add Bootstrap utility class overrides**

```css
/* === Bootstrap Utility Class Overrides for Dark Theme === */
.bg-primary { background-color: var(--obs-primary) !important; }
.bg-success { background-color: var(--obs-success) !important; }
.bg-danger { background-color: var(--obs-danger) !important; }
.bg-warning { background-color: var(--obs-warning) !important; }
.bg-secondary { background-color: var(--obs-surface-alt) !important; color: var(--obs-text-secondary); }
.bg-info { background-color: var(--obs-info) !important; }
.bg-light { background-color: var(--obs-surface) !important; }
.bg-white { background-color: var(--obs-surface) !important; }
.bg-dark { background-color: var(--obs-bg) !important; }

.text-primary { color: var(--obs-primary-light) !important; }
.text-success { color: var(--obs-success-light) !important; }
.text-danger { color: var(--obs-danger-light) !important; }
.text-warning { color: var(--obs-warning-light) !important; }
.text-info { color: var(--obs-info-light) !important; }
.text-secondary { color: var(--obs-text-secondary) !important; }
.text-muted { color: var(--obs-text-muted) !important; }
.text-dark { color: var(--obs-text) !important; }
.text-white { color: #fff !important; }

.table-dark {
    --bs-table-bg: var(--obs-surface-alt);
    --bs-table-color: var(--obs-text);
    --bs-table-border-color: var(--obs-border);
}
```

- [ ] **Step 12: Rewrite loading, chart, number display styles**

```css
/* Chart container */
.chart-container-financial {
    background: var(--obs-surface);
    border: 1px solid var(--obs-border);
    border-radius: var(--border-radius-lg);
    padding: var(--spacing-4);
    margin: var(--spacing-4) 0;
    position: relative;
    overflow: hidden;
}

.chart-container-financial::before { display: none; }

/* Number display */
.number-display {
    font-weight: 700;
    font-size: var(--font-size-2xl);
}

.number-display::after { display: none; }

/* Loading */
.loading-spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--obs-border);
    border-top: 3px solid var(--obs-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: var(--spacing-3);
}

.loading-text {
    color: var(--obs-text-muted);
    font-weight: 500;
    font-size: var(--font-size-sm);
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
```

- [ ] **Step 13: Add scrollbar, animation, and section title styles**

```css
/* Custom Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--obs-bg); }
::-webkit-scrollbar-thumb { background: var(--obs-border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--gray-400); }

/* Staggered fade-in animation */
@keyframes obsFadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

.obs-animate > * {
    opacity: 0;
    animation: obsFadeIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
.obs-animate > *:nth-child(1) { animation-delay: 0ms; }
.obs-animate > *:nth-child(2) { animation-delay: 50ms; }
.obs-animate > *:nth-child(3) { animation-delay: 100ms; }
.obs-animate > *:nth-child(4) { animation-delay: 150ms; }
.obs-animate > *:nth-child(5) { animation-delay: 200ms; }
.obs-animate > *:nth-child(6) { animation-delay: 250ms; }

/* Section title with Indigo bar */
.section-title {
    color: var(--obs-text);
    font-size: 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 1rem;
}

.section-title::before {
    content: '';
    width: 3px;
    height: 16px;
    background: var(--obs-primary);
    border-radius: 2px;
    flex-shrink: 0;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

/* High contrast */
@media (prefers-contrast: high) {
    .card, .card-financial { border-width: 2px; }
}

/* Focus indicators */
.btn:focus, .nav-link:focus {
    outline: 2px solid var(--obs-primary);
    outline-offset: 2px;
}
```

- [ ] **Step 14: Remove old animations and responsive adjustments**

Remove `@keyframes fadeInUp`, `@keyframes fadeInLeft`, `@keyframes pulse`, `@keyframes shimmer` and their associated classes. Replace with the `obsFadeIn` above.

Keep the `@media (max-width: 768px)` block but update all color references to use Obsidian tokens. Reduce metric-icon size for mobile.

- [ ] **Step 15: Commit**

```bash
git add app/static/css/financial-theme.css
git commit -m "style: rewrite financial-theme.css with Obsidian dark tokens"
```

---

### Task 2: Update responsive-financial.css for Dark Theme

**Files:**
- Modify: `app/static/css/responsive-financial.css`

- [ ] **Step 1: Replace all light-theme color values**

Find and replace these patterns throughout the file:

| Old | New |
|-----|-----|
| `rgba(255, 255, 255, 0.95)` (navbar collapse bg) | `rgba(15, 23, 42, 0.98)` |
| `rgba(255, 255, 255, 0.1)` (toggler bg) | `rgba(99, 102, 241, 0.2)` |
| `rgba(255, 255, 255, 0.25)` (focus shadow) | `rgba(99, 102, 241, 0.25)` |
| `background: white` / `background-color: white` | `background: var(--obs-surface)` |
| `linear-gradient(135deg, var(--gray-50), white)` | `var(--obs-surface)` |
| `var(--primary-color)` in outlines | `var(--obs-primary)` |

For the navbar collapse, the background needs to be dark instead of light:
```css
.navbar-financial .navbar-collapse {
    background: rgba(15, 23, 42, 0.98);
    backdrop-filter: blur(10px);
    margin-top: 1rem;
    border-radius: var(--border-radius-lg);
    border: 1px solid var(--obs-border);
}
```

For the mobile nav links inside the collapse:
```css
.navbar-financial .navbar-collapse .nav-link {
    color: var(--obs-text-secondary) !important;
    border-bottom: 1px solid var(--obs-border);
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/css/responsive-financial.css
git commit -m "style: update responsive CSS for Obsidian dark theme"
```

---

### Task 3: Update base.html

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 1: Add DM Sans Google Fonts link**

Before the Bootstrap CSS link (line 9), add:

```html
<!-- DM Sans Font -->
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Rewrite inline `<style>` block**

Replace the entire `<style>` block (lines 21-367) with only the mobile responsive styles that are NOT handled by `financial-theme.css`. Remove:
- The `stock-info` gradient (line 39)
- The `@media (prefers-color-scheme: dark)` block (lines 318-332) entirely
- The `.btn-purple` styles
- The `metric-card:hover { transform: translateY(-2px) }`

Keep only:
- Mobile container padding adjustments
- Mobile card/table/button form factor adjustments (update colors to Obsidian)
- iOS touch target rules
- `@media (prefers-reduced-motion: reduce)` block
- `@media (-webkit-min-device-pixel-ratio: 2)` block

For all mobile-specific color overrides in the kept rules, use Obsidian tokens.

- [ ] **Step 3: Update navbar brand HTML**

Replace lines 375-378:

```html
<a class="navbar-brand d-flex align-items-center" href="{{ url_for('main.index') }}">
    <div style="width:28px;height:28px;border-radius:6px;background:linear-gradient(135deg,#6366f1,#818cf8);display:flex;align-items:center;justify-content:center;margin-right:8px;">
        <span style="color:#fff;font-size:12px;font-weight:700;">Q</span>
    </div>
    <span>QuantAnalysis</span>
</a>
```

- [ ] **Step 4: Update real-time indicator**

Replace lines 442-444:

```html
<span class="real-time-indicator">Live</span>
```

- [ ] **Step 5: Update refresh button**

Replace lines 446-449:

```html
<button class="btn btn-outline-light btn-sm" onclick="location.reload()" style="border-color:rgba(100,116,139,0.3);color:#64748b;">
    <i class="fas fa-sync-alt me-1"></i>刷新
</button>
```

- [ ] **Step 6: Update main content margin**

Change line 456 `margin-top: 76px` to `margin-top: 56px` (matching new navbar height).

- [ ] **Step 7: Update ECharts theme**

Replace the `financialTheme` object (lines 521-581) with Obsidian colors:

```javascript
const financialTheme = {
    color: ['#6366f1', '#818cf8', '#4ade80', '#fbbf24', '#22d3ee', '#f87171', '#a78bfa', '#34d399'],
    backgroundColor: 'transparent',
    textStyle: {
        fontFamily: "'DM Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif",
        color: '#94a3b8'
    },
    title: { textStyle: { color: '#e2e8f0', fontWeight: 600 } },
    legend: { textStyle: { color: '#94a3b8' } },
    grid: { borderColor: '#334155' },
    categoryAxis: {
        axisLine: { lineStyle: { color: '#334155' } },
        axisTick: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#64748b' },
        splitLine: { lineStyle: { color: 'rgba(51,65,85,0.5)' } }
    },
    valueAxis: {
        axisLine: { lineStyle: { color: '#334155' } },
        axisTick: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#64748b' },
        splitLine: { lineStyle: { color: 'rgba(51,65,85,0.5)' } }
    }
};
```

- [ ] **Step 8: Commit**

```bash
git add app/templates/base.html
git commit -m "style: update base.html with Obsidian navbar, fonts, ECharts theme"
```

---

### Task 4: Delete mobile.css

**Files:**
- Delete: `app/static/css/mobile.css`

- [ ] **Step 1: Verify mobile.css is not loaded**

Run: `grep -r "mobile.css" app/templates/`
Expected: no results (confirmed dead code).

- [ ] **Step 2: Delete**

```bash
git rm app/static/css/mobile.css
git commit -m "chore: delete dead mobile.css (not loaded by any template)"
```

---

### Task 5: Update index.html

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Remove emoji from headings**

Replace:
- `<h1 class="display-4 mb-3">📈 股票分析系统</h1>` → `<h1 class="display-4 mb-3">股票量化分析系统</h1>`
- `<h2 class="mb-4">🚀 核心功能</h2>` → `<h2 class="section-title">核心功能</h2>`
- `<h2 class="mb-2">⚡ 实时交易分析系统（部分能力持续整改中）</h2>` → `<h2 class="section-title">实时交易分析系统</h2>`
- `<h2 class="mb-4">📊 数据概览</h2>` → `<h2 class="section-title">数据概览</h2>`
- `<h2 class="mb-4">✨ 系统特性</h2>` → `<h2 class="section-title">系统特性</h2>`
- `<h2 class="mb-4">🧠 多因子模型系统</h2>` → `<h2 class="section-title">多因子模型系统</h2>`

- [ ] **Step 2: Replace `{% block extra_css %}` content**

Remove the entire `{% block extra_css %}` block (lines 5-126). The responsive styles are now handled globally by the updated `financial-theme.css` and `responsive-financial.css`.

- [ ] **Step 3: Add obs-animate class to card grids**

Add `obs-animate` class to the card grid `<div class="row">` elements that contain feature cards (4 instances).

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html
git commit -m "style: update index.html for Obsidian theme"
```

---

### Task 6: Update analysis.html

**Files:**
- Modify: `app/templates/analysis.html`

- [ ] **Step 1: Remove emoji from heading**

Replace `<h1 class="h2">📈 技术分析</h1>` → `<h1 class="h2">技术分析</h1>`

- [ ] **Step 2: Replace `{% block extra_css %}` content**

Remove all light-theme inline styles in the extra_css block:
- `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)` → remove or replace with `background: var(--obs-surface); border: 1px solid var(--obs-border-light);`
- `background-color: #f8f9fa` → remove
- `#dee2e6` border → `var(--obs-border)`
- `#007bff` colors → `var(--obs-primary)`

- [ ] **Step 3: Commit**

```bash
git add app/templates/analysis.html
git commit -m "style: update analysis.html for Obsidian theme"
```

---

### Task 7: Update remaining core pages (stocks, screen, backtest, stock_detail)

**Files:**
- Modify: `app/templates/stocks.html`
- Modify: `app/templates/screen.html`
- Modify: `app/templates/backtest.html`
- Modify: `app/templates/stock_detail.html`

- [ ] **Step 1: For each file, remove emoji from headings**

Search for emoji characters (📈🚀📊🧠⭐💼🔄⚡✨🎯) in `<h1>` and `<h2>` tags and remove them. The Bootstrap utility class overrides from Task 1 will handle `bg-*`, `text-success`, `text-danger` etc.

- [ ] **Step 2: Remove any page-specific light-theme inline styles**

If any file has `{% block extra_css %}` with light-theme colors, replace with Obsidian equivalents or remove.

- [ ] **Step 3: Commit**

```bash
git add app/templates/stocks.html app/templates/screen.html app/templates/backtest.html app/templates/stock_detail.html
git commit -m "style: update core pages for Obsidian theme"
```

---

### Task 8: Update ML Factor pages

**Files:**
- Modify: `app/templates/ml_factor/index.html`
- Modify: `app/templates/ml_factor/analysis.html`
- Modify: `app/templates/ml_factor/backtest.html`
- Modify: `app/templates/ml_factor/models.html`
- Modify: `app/templates/ml_factor/portfolio.html`
- Modify: `app/templates/ml_factor/scoring.html`

- [ ] **Step 1: Remove emoji from each h1 heading**

| File | Old | New |
|------|-----|-----|
| `index.html` | `🧠 因子管理` | `因子管理` |
| `analysis.html` | `📊 分析视图` | `分析视图` |
| `backtest.html` | `🔄 回测验证` | `回测验证` |
| `models.html` | `🧠 模型管理` | `模型管理` |
| `portfolio.html` | `💼 投资组合` | `投资组合` |
| `scoring.html` | `⭐ 股票评分` | `股票评分` |

- [ ] **Step 2: Commit**

```bash
git add app/templates/ml_factor/
git commit -m "style: update ML factor pages for Obsidian theme"
```

---

### Task 9: Update Realtime Analysis pages

**Files:**
- Modify: `app/templates/realtime_analysis/index.html`
- Modify: `app/templates/realtime_analysis/indicators.html`
- Modify: `app/templates/realtime_analysis/monitor.html`
- Modify: `app/templates/realtime_analysis/report_management.html`
- Modify: `app/templates/realtime_analysis/risk_management.html`
- Modify: `app/templates/realtime_analysis/signals.html`
- Modify: `app/templates/realtime_analysis/websocket_management.html`

- [ ] **Step 1: `index.html` — no extra_css block, no emoji. Only has `text-primary` on icon. Bootstrap override handles it. No changes needed.**

- [ ] **Step 2: `indicators.html` — has extra_css with purple gradient and status colors**

Replace inline styles:
- `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)` → `background: var(--obs-surface); border: 1px solid var(--obs-border-light);`
- `background-color: #f8f9fa` → `background-color: var(--obs-surface)`
- `border: 1px solid #dee2e6` → `border: 1px solid var(--obs-border)`
- `.status-success { background-color: #28a745; }` → `.status-success { background-color: var(--obs-success); }`
- `.status-warning { background-color: #ffc107; }` → `.status-warning { background-color: var(--obs-warning); }`
- `.status-danger { background-color: #dc3545; }` → `.status-danger { background-color: var(--obs-danger); }`
- `color: white` on gradient → remove (text inherits from card)

- [ ] **Step 3: `monitor.html` — has extra_css with light backgrounds and A-share color convention**

Replace inline styles:
- `background-color: #f8f9fa` → `background-color: var(--obs-surface)`
- `border: 1px solid #eee` → `border: 1px solid var(--obs-border)`
- `background: rgba(255,255,255,0.8)` → `background: var(--obs-surface)`
- `.positive { color: #dc3545; }` → `.positive { color: var(--obs-danger-light); }` (A-share: red=up)
- `.negative { color: #198754; }` → `.negative { color: var(--obs-success-light); }` (A-share: green=down)
- `.neutral { color: #6c757d; }` → `.neutral { color: var(--obs-text-muted); }`

- [ ] **Step 4: `report_management.html` — has extra_css with colored borders**

Replace inline styles:
- `border-left: 4px solid #0d6efd` → `border-left: 4px solid var(--obs-primary)`
- `.template-card { border-left-color: #198754; }` → `.template-card { border-left-color: var(--obs-success); }`
- `.subscription-card { border-left-color: #ffc107; }` → `.subscription-card { border-left-color: var(--obs-warning); }`
- `background: #f8f9fa` → `background: var(--obs-surface)`

- [ ] **Step 5: `risk_management.html` — has extensive extra_css with status and alert colors**

Replace inline styles:
- `border-left: 4px solid #007bff` → `border-left: 4px solid var(--obs-primary)`
- `.risk-high { border-left-color: #dc3545; }` → `.risk-high { border-left-color: var(--obs-danger); }`
- `.risk-medium { border-left-color: #ffc107; }` → `.risk-medium { border-left-color: var(--obs-warning); }`
- `.risk-low { border-left-color: #28a745; }` → `.risk-low { border-left-color: var(--obs-success); }`
- `.alert-high { background-color: #f8d7da; }` → `.alert-high { background-color: var(--obs-danger-bg); }`
- `.alert-medium { background-color: #fff3cd; }` → `.alert-medium { background-color: var(--obs-warning-bg); }`
- `.alert-low { background-color: #d1eddd; }` → `.alert-low { background-color: var(--obs-success-bg); }`
- `background-color: #f8f9fa` → `background-color: var(--obs-surface)`
- `background-color: #007bff` → `background-color: var(--obs-primary)`
- `.status-online { background-color: #28a745; }` → `.status-online { background-color: var(--obs-success); }`
- `.status-warning { background-color: #ffc107; }` → `.status-warning { background-color: var(--obs-warning); }`
- `.status-offline { background-color: #dc3545; }` → `.status-offline { background-color: var(--obs-danger); }`

- [ ] **Step 6: `signals.html` — has extra_css with signal gradients and light backgrounds**

Replace inline styles:
- `.signal-buy { background: linear-gradient(90deg, #28a745, #20c997); }` → `.signal-buy { background: var(--obs-success); }`
- `.signal-sell { background: linear-gradient(90deg, #dc3545, #fd7e14); }` → `.signal-sell { background: var(--obs-danger); }`
- `.signal-hold { background: linear-gradient(90deg, #6c757d, #adb5bd); }` → `.signal-hold { background: var(--obs-border); }`
- `background-color: #f8f9fa` → `background-color: var(--obs-surface)`
- `border: 1px solid #dee2e6` → `border: 1px solid var(--obs-border)`

- [ ] **Step 7: `websocket_management.html` — has extra_css with status colors and message backgrounds**

Replace inline styles:
- `.status-connected { background-color: #28a745; }` → `.status-connected { background-color: var(--obs-success); }`
- `.status-disconnected { background-color: #dc3545; }` → `.status-disconnected { background-color: var(--obs-danger); }`
- `.status-connecting { background-color: #ffc107; }` → `.status-connecting { background-color: var(--obs-warning); }`
- `background-color: #f8f9fa` → `background-color: var(--obs-surface)` (2 occurrences)
- `border: 1px solid #dee2e6` → `border: 1px solid var(--obs-border)` (2 occurrences)
- `.message-info { background-color: #d1ecf1; }` → `.message-info { background-color: var(--obs-info-bg); }`
- `.message-success { background-color: #d4edda; }` → `.message-success { background-color: var(--obs-success-bg); }`
- `.message-warning { background-color: #fff3cd; }` → `.message-warning { background-color: var(--obs-warning-bg); }`
- `.message-error { background-color: #f8d7da; }` → `.message-error { background-color: var(--obs-danger-bg); }`

- [ ] **Step 8: Commit**

```bash
git add app/templates/realtime_analysis/
git commit -m "style: update realtime analysis pages for Obsidian theme"
```

---

### Task 10: Update data_management/index.html

**Files:**
- Modify: `app/templates/data_management/index.html`

- [ ] **Step 1: Replace light-theme inline styles**

Same replacements as Task 9 for:
- Purple gradient (#667eea → #764ba2) → `var(--obs-surface)` + border
- Status colors (#28a745, #ffc107, #dc3545) → Obsidian semantic colors
- `#f8f9fa` backgrounds → `var(--obs-surface)`

- [ ] **Step 2: Commit**

```bash
git add app/templates/data_management/index.html
git commit -m "style: update data management page for Obsidian theme"
```

---

### Task 11: Convert text2sql/index.html to extend base.html

**Files:**
- Rewrite: `app/templates/text2sql/index.html`

This is the most complex template change. The file is currently a standalone HTML document (does NOT extend base.html).

**Prerequisites:** Task 1 (CSS tokens + Bootstrap overrides) and Task 3 (base.html navbar) must be completed first.

- [ ] **Step 0: Verify prerequisites**

```bash
grep -c "obs-primary" app/static/css/financial-theme.css
grep -c "bg-primary.*obs-primary" app/static/css/financial-theme.css
grep -c "QuantAnalysis" app/templates/base.html
```

Expected: all counts > 0. If any is 0, complete the prerequisite task first.

- [ ] **Step 1: Add template inheritance**

At the top of the file, add:
```html
{% extends "base.html" %}
```

Remove the entire `<!DOCTYPE html>`, `<html>`, `<head>`, and `</html>` wrapper. Keep only the `<body>` content.

- [ ] **Step 2: Wrap content in blocks**

Move CSS into `{% block extra_css %}<style>...</style>{% endblock %}`.
Move the main body content into `{% block content %}...{% endblock %}`.
Move JS into `{% block extra_js %}<script>...</script>{% endblock %}`.

- [ ] **Step 3: Remove the standalone navbar**

Delete the `<nav>` element — the navbar is now inherited from base.html.

- [ ] **Step 4: Replace light-theme inline styles**

Replace all light-theme colors in the remaining `<style>` block:

- `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)` → `background: var(--obs-surface); border: 1px solid var(--obs-border-light);`
- `background-color: #f8f9fa` → `background-color: var(--obs-surface)`
- `.chat-container { border: 2px solid #dee2e6; }` → `.chat-container { border: 1px solid var(--obs-border); }`
- `.user-message { background-color: #007bff; color: white; }` → `.user-message { background-color: var(--obs-primary); color: white; }`
- `.assistant-message { background-color: #f8f9fa; }` → `.assistant-message { background-color: var(--obs-surface-alt); }`
- `.statistics-card { background: linear-gradient(135deg, #ff6b9d 0%, #c44dff 100%); }` → `.statistics-card { background: var(--obs-primary-bg); border: 1px solid var(--obs-border-light); }`
- `.query-item { background-color: #f8f9fa; border: 1px solid #dee2e6; }` → `.query-item { background-color: var(--obs-surface); border: 1px solid var(--obs-border); }`
- All `color: #333` / `color: #666` → `color: var(--obs-text)` / `color: var(--obs-text-secondary)`

- [ ] **Step 5: Verify JS-generated HTML classes work with Bootstrap overrides**

**Do NOT modify JS template strings.** Task 1's global Bootstrap utility overrides handle all of these:

- `badge bg-primary` → overridden to `background-color: var(--obs-primary)`
- `badge bg-success` → overridden to `background-color: var(--obs-success)`
- `badge bg-danger` → overridden to `background-color: var(--obs-danger)`
- `text-muted` → overridden to `color: var(--obs-text-muted)`
- `thead class="table-dark"` → overridden with `--bs-table-bg: var(--obs-surface-alt)`

Run a quick verification after committing:
```bash
grep -n "bg-primary\|bg-success\|bg-danger\|table-dark\|text-muted" app/templates/text2sql/index.html | head -20
```

Confirm these classes exist in JS template strings and that the global CSS overrides from Task 1 will apply to them. If any class is NOT covered by Task 1's overrides (Step 11), add it there.

- [ ] **Step 6: Commit**

```bash
git add app/templates/text2sql/index.html
git commit -m "style: convert text2sql to extend base.html with Obsidian theme"
```

---

### Task 12: Visual Verification

**Files:**
- Verify: all modified files

- [ ] **Step 1: Start the app**

```bash
cd /Users/henrylin/quant_space/quantitative_analysis && python run.py
```

Expected: app starts without template errors.

- [ ] **Step 2: Verify key pages**

Open each URL and check for:
- Dark background, readable text
- Cards with correct borders and hover effects
- Tables with correct header/row colors
- Forms with dark inputs and visible text
- Buttons with correct colors and no translateY
- No emoji in headings
- Indigo accent colors throughout

Pages to check:
- `/` (homepage)
- `/stocks` (stock list)
- `/analysis` (technical analysis)
- `/ml-factor` (factor management)
- `/ml-factor/scoring` (scoring)
- `/ml-factor/portfolio` (portfolio)
- `/ml-factor/models` (models)
- `/realtime-analysis` (realtime dashboard)
- `/data-management` (data management)

- [ ] **Step 3: Check ECharts rendering**

On the analysis page, verify charts render with Obsidian colors (dark grid, Indigo series colors, readable labels).

- [ ] **Step 4: Run test suite**

```bash
pytest -q
```

Expected: all tests pass or only pre-existing environment failures.

- [ ] **Step 5: Fix any visual regressions**

If any page has obvious issues, fix in the relevant CSS or template file.

```bash
git add -A
git commit -m "style: fix Obsidian theme visual regressions"
```
