# Obsidian Theme Redesign — Frontend Design Spec

Date: 2026-06-04

## Context

The current Flask/Jinja frontend uses Bootstrap 5, Font Awesome, and a custom `financial-theme.css` with a blue gradient navbar, white card surfaces, and light backgrounds. The visual style is functional but generic — oversized buttons, inconsistent dark mode, strong gradients, and a lack of cohesive identity.

This redesign replaces the entire visual layer with an **Obsidian** aesthetic: deep dark surfaces, Indigo accent colors, DM Sans typography, and restrained micro-animations. The goal is a distinctive, modern financial dashboard that feels like a professional quant tool.

## Goals

- Transform the entire site into a cohesive Obsidian dark theme with Indigo (#6366f1) as the primary accent color.
- Replace the current system font stack with DM Sans (loaded via Google Fonts CDN) for Latin text, with system Chinese fallbacks.
- Add restrained micro-animations: page fade-in, button hover states, card hover borders, and a subtle glow effect on the navbar.
- Make all pages consistently use the new design tokens — navbar, cards, tables, forms, buttons, modals, alerts, badges.
- Update ECharts theme to match the Obsidian palette for dark surfaces.
- Keep all existing functionality, API behavior, and template structure unchanged. Only presentation layer is modified.

## Non-Goals

- Rebuild the design system from scratch or replace Bootstrap.
- Change navigation structure, page information architecture, or route definitions.
- Add a manual light/dark theme toggle — this is a permanent dark theme.
- Rewrite JavaScript logic, API endpoints, or data flows.
- Add new pages or features.
- Restyle `api_test.html` — it is a developer/debug page. Leave as-is.

## Decisions

### Standalone Pages

Two templates do **not** extend `base.html` and have their own full HTML document:

1. **`text2sql/index.html`** — Has its own navbar, inline styles with light-theme colors, and extensive JS-generated HTML using Bootstrap utility classes (`bg-primary`, `bg-success`, `bg-danger`, `table-dark`, `text-muted`). This page will be **converted to extend `base.html`** so it inherits the Obsidian theme automatically. Its standalone navbar and styles will be removed. JS-generated HTML classes (`bg-primary`, `bg-success`, etc.) will be replaced with Obsidian-compatible custom classes.

2. **`api_test.html`** — Developer debug page. **Left as-is** (see Non-Goals).

### Dead CSS: `mobile.css`

The file `app/static/css/mobile.css` (588 lines) is **not loaded** by any template — it is dead code. It will be **deleted** as part of this redesign to avoid confusion.

### Bootstrap Override Strategy

Bootstrap 5 ships with light-theme defaults for all components. Since this is a permanent dark theme, we override Bootstrap selectors **directly** in `financial-theme.css` using the same specificity as Bootstrap (no `!important` unless necessary for Bootstrap utility class overrides). The `body` element sets the base: `background-color: var(--obs-bg); color: var(--obs-text);`. For JS-generated Bootstrap utility classes (`bg-primary`, `bg-success`, `bg-danger`, `bg-warning`, `bg-secondary`, `text-success`, `text-danger`, `text-muted`), we add global overrides in `financial-theme.css`:

```css
/* Override Bootstrap utility classes for dark theme */
.bg-primary { background-color: var(--obs-primary) !important; }
.bg-success { background-color: var(--obs-success) !important; }
.bg-danger { background-color: var(--obs-danger) !important; }
.bg-warning { background-color: var(--obs-warning) !important; }
.bg-secondary { background-color: var(--obs-surface) !important; }
.bg-info { background-color: var(--obs-info) !important; }
.text-success { color: var(--obs-success-light) !important; }
.text-danger { color: var(--obs-danger-light) !important; }
.text-muted { color: var(--obs-text-muted) !important; }
.table-dark { --bs-table-bg: var(--obs-surface-alt); --bs-table-color: var(--obs-text); }
```

This avoids modifying JS template strings in every template.

## Visual Direction

**Aesthetic**: Obsidian — deep dark surfaces with Indigo accents. Inspired by Linear, Vercel, and Raycast dashboards.

**Mood**: Calm, professional, high-density. A tool you use for hours without visual fatigue.

**Signature element**: The Indigo accent bar/glow on cards and the navbar. The monochrome icon containers with colored accents. The capsule-shaped score badges.

### Color Tokens

```
/* Surfaces */
--obs-bg:           #0f172a      /* Page background */
--obs-surface:      #1e293b      /* Card / elevated surface */
--obs-surface-alt:  #162033      /* Table header / subtle surface */
--obs-border:       #334155      /* Default border */
--obs-border-light: rgba(99,102,241,0.15)  /* Accent border (hover, focus) */

/* Text */
--obs-text:         #e2e8f0      /* Primary text */
--obs-text-secondary: #94a3b8    /* Secondary text */
--obs-text-muted:   #64748b      /* Muted / placeholder text */

/* Brand / Accent */
--obs-primary:      #6366f1      /* Indigo 500 */
--obs-primary-light:#818cf8      /* Indigo 400 */
--obs-primary-bg:   rgba(99,102,241,0.10)   /* Primary surface tint */

/* Semantic */
--obs-success:      #22c55e      /* Green 500 */
--obs-success-light:#4ade80      /* Green 400 */
--obs-warning:      #f59e0b      /* Amber 500 */
--obs-warning-light:#fbbf24      /* Amber 400 */
--obs-danger:       #ef4444      /* Red 500 */
--obs-danger-light: #f87171      /* Red 400 */
--obs-info:         #06b6d4      /* Cyan 500 */
--obs-info-light:   #22d3ee      /* Cyan 400 */
```

### Typography

- **Primary font**: DM Sans (Google Fonts CDN: `https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap`)
- **Chinese fallback**: `"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`
- **Font stack**: `'DM Sans', "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`
- Body text: 14px / 0.875rem, line-height 1.55
- Page titles: 24-28px, font-weight 600
- Card titles: 15-16px, font-weight 600
- Table text: 13px
- Labels / small text: 12px

### Motion

All transitions use `cubic-bezier(0.4, 0, 0.2, 1)` (ease-out curve) for a polished feel.

- **Page load**: Cards and sections fade in with `opacity 0→1` and `translateY(8px)→0` over 300ms, staggered via `animation-delay` (50ms between siblings).
- **Card hover**: Border color shifts to `--obs-border-light`, subtle `box-shadow: 0 0 20px rgba(99,102,241,0.08)`. No translate/lift.
- **Button hover**: Background brightens slightly. Primary buttons get a subtle glow `box-shadow: 0 0 16px rgba(99,102,241,0.25)`. No translate.
- **Nav link hover**: Background fills with `rgba(99,102,241,0.12)`. Active state shows Indigo text + same background.
- **Loading spinner**: Uses Indigo border instead of current blue.
- **Reduced motion**: `prefers-reduced-motion: reduce` disables all animations and transitions.

## Component Specifications

### Navbar (`.navbar-financial`)

- Background: `linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)`
- Border-bottom: `1px solid rgba(99,102,241,0.15)`
- Height: 56px
- Backdrop-filter: `blur(12px)` (subtle glass effect)
- Brand: Indigo gradient square icon (28×28, rounded 6px) + "QuantAnalysis" in DM Sans 600
- Nav links: `color: #94a3b8`, hover/active: `color: #818cf8` + `background: rgba(99,102,241,0.12)`, border-radius 6px
- Dropdown: `background: #1e293b`, `border: 1px solid #334155`, rounded 10px, items use `--obs-text` with Indigo hover
- Real-time indicator: Green dot + "Live" text, `background: rgba(34,197,94,0.15)`, `color: #4ade80`, pill shape
- Refresh button: Ghost style, `border: 1px solid rgba(100,116,139,0.3)`, `color: #64748b`

### Hero Banner (`.stock-info-banner`)

- Remove the current purple gradient background
- Replace with: `background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.05))`, `border: 1px solid rgba(99,102,241,0.15)`, rounded 12px
- Top glow line: `height: 1px` gradient line at 10%-90% horizontal span, `rgba(99,102,241,0.4)` center
- Title: `color: #e2e8f0`, DM Sans, 28px, weight 700, remove emoji prefix
- Subtitle: `color: #818cf8`, 14px
- Description: `color: #64748b`, 13px
- Buttons: Primary = Indigo solid with glow shadow. Secondary = ghost with Indigo border.
- Remove emoji from heading text (use clean text only)

### Cards (`.card`, `.card-financial`, `.metric-card-enhanced`)

- Background: `#1e293b`
- Border: `1px solid #334155`
- Border-radius: 10px
- Hover: `border-color: rgba(99,102,241,0.3)`, `box-shadow: 0 0 20px rgba(99,102,241,0.06)`. No translateY.
- Remove existing `transform: translateY(-2px)` and `scale(1.01)` hover effects
- Remove the `::before` gradient top bar animation on `.metric-card-enhanced`
- Card header: `background: #162033`, `border-bottom: 1px solid #334155`
- Card body padding: 1rem (reduced from current)

### Metric Icon Containers

- Size: 36×36px (reduced from 64px)
- Background: Semantic tinted (e.g., `rgba(99,102,241,0.1)` for primary)
- Border-radius: 8px
- Icon color matches semantic tint (e.g., `#818cf8` for primary)
- Remove the rotate/scale hover animation on `.metric-card-enhanced:hover .metric-icon`

### Buttons (`.btn`, `.btn-financial`)

- Font: DM Sans, weight 500
- Border-radius: 8px
- Remove all `translateY(-2px)` hover effects
- Remove the shimmer `::before` sweep animation
- Primary button: `background: #6366f1`, hover glow `box-shadow: 0 0 16px rgba(99,102,241,0.25)`
- Success: `background: #059669`
- Warning: `background: #d97706`
- Danger: `background: #dc2626`
- Ghost/outline: `background: transparent`, `border: 1px solid rgba(99,102,241,0.3)`, `color: #818cf8`
- Small buttons: font-size 12px, padding 4px 12px

### Tables (`.table`, `.table-financial`)

- Background: `#1e293b`
- Table header: `background: #162033`, `color: #64748b`, font-size 12px, uppercase, letter-spacing 0.05em
- Table rows: `color: #e2e8f0`, font-size 13px
- Row borders: `border-bottom: 1px solid rgba(51,65,85,0.5)`
- Hover: `background: rgba(99,102,241,0.06)`
- Remove `transform: scale(1.01)` on row hover
- Score/numeric badges: capsule shape, e.g. `background: rgba(99,102,241,0.15)`, `color: #818cf8`, `padding: 2px 8px`, `border-radius: 10px`
- Positive values: `color: #4ade80`
- Negative values: `color: #f87171`

### Forms (`.form-control`, `.form-select`, `.form-label`)

- Input background: `#162033`
- Input border: `#334155`
- Input text: `#e2e8f0`
- Placeholder: `#64748b`
- Focus border: `rgba(99,102,241,0.5)` with `box-shadow: 0 0 0 2px rgba(99,102,241,0.15)`
- Label: `color: #94a3b8`, font-size 12px, font-weight 500
- Select: same as input, dropdown arrow in `#64748b`

### Modals (`.modal-content`)

- Background: `#1e293b`
- Border: `1px solid #334155`
- Header: `border-bottom: 1px solid #334155`
- Footer: `border-top: 1px solid #334155`
- Close button: `color: #64748b`, hover `color: #e2e8f0`

### Alerts (`.alert`)

- Danger: `background: rgba(239,68,68,0.10)`, `border-left: 3px solid #ef4444`, `color: #f87171`
- Success: `background: rgba(34,197,94,0.10)`, `border-left: 3px solid #22c55e`, `color: #4ade80`
- Warning: `background: rgba(245,158,11,0.10)`, `border-left: 3px solid #f59e0b`, `color: #fbbf24`
- Info: `background: rgba(6,182,212,0.10)`, `border-left: 3px solid #06b6d4`, `color: #22d3ee`

### Badges (`.badge`)

- Background uses semantic tint (e.g., `rgba(99,102,241,0.15)`)
- Text uses semantic light color (e.g., `#818cf8`)
- Border-radius: 10px (capsule)
- Font-size: 11px

### Dropdowns (`.dropdown-menu`)

- Background: `#1e293b`
- Border: `1px solid #334155`
- Border-radius: 10px
- Items: `color: #e2e8f0`, hover: `background: rgba(99,102,241,0.08)`, `color: #818cf8`

### Section Titles (pages)

- Style: `color: #e2e8f0`, font-size 16px, font-weight 600
- Prefix: 3px-wide Indigo bar on the left (`width: 3px, height: 16px, background: #6366f1, border-radius: 2px`)
- Remove emoji prefixes from section headings (use the Indigo bar instead)

### ECharts Theme

Update the `financialTheme` object in `base.html`:
- Background: `transparent`
- Text colors: `#94a3b8` (axis labels), `#e2e8f0` (title)
- Grid lines: `#334155`
- Series colors: `['#6366f1', '#818cf8', '#4ade80', '#fbbf24', '#22d3ee', '#f87171', '#a78bfa', '#34d399']`
- Axis lines: `#334155`

### Loading Spinner

- Border: `3px solid #334155`
- Border-top: `3px solid #6366f1`
- Size: 32px

### Scrollbar (desktop)

- Track: `#0f172a`
- Thumb: `#334155`, hover `#475569`
- Width: 6px, border-radius: 3px

## Template Changes

### `base.html`

1. Add Google Fonts `<link>` for DM Sans before Bootstrap CSS
2. **Remove** the `@media (prefers-color-scheme: dark)` block (lines 318-332) entirely — redundant with permanent dark theme
3. **Remove** the `stock-info` gradient and `.btn-purple` styles
4. Keep all structural responsive media queries (768px, 576px, landscape, touch, high-DPI) but replace all color values with Obsidian tokens
5. Keep the `@media (prefers-reduced-motion: reduce)` block as-is
6. Update navbar HTML: replace Font Awesome chart-line icon with the Indigo gradient "Q" brand block, update brand text to "QuantAnalysis"
7. Update real-time indicator to green pill with "Live" text
8. Update refresh button to ghost style
9. Update ECharts theme registration to use Obsidian colors

### `financial-theme.css`

1. Replace `:root` variables entirely with Obsidian tokens
2. Rewrite all component selectors to use Obsidian tokens
3. Remove all gradient backgrounds on buttons, cards, banners
4. Remove all `translateY` hover effects
5. Remove all `transform: scale()` hover effects
6. Add staggered fade-in animation for card grids
7. Add custom scrollbar styles
8. Update alert styles to use tinted backgrounds with left border
9. Remove emoji from CSS-generated content (none currently, but ensure clean)

### `responsive-financial.css`

Adjust responsive breakpoints to work with dark theme colors. No structural layout changes.

### Page Templates

For each page template (`index.html`, `stocks.html`, `analysis.html`, `screen.html`, `backtest.html`, `stock_detail.html`, `ml_factor/*.html`, `realtime_analysis/*.html`, `data_management/index.html`):

1. Remove emoji from `<h1>`, `<h2>` headings — replace with plain text
2. Replace section emoji prefixes with the Indigo bar pattern (CSS class or inline style)
3. Remove any page-specific inline `<style>` that sets light-theme colors — let the global Obsidian tokens handle it
4. Keep all JavaScript, API calls, and HTML structure unchanged

## Files Modified

| File | Change Type |
|------|------------|
| `app/templates/base.html` | Navbar redesign, font import, ECharts theme, inline styles rewrite |
| `app/static/css/financial-theme.css` | Full rewrite with Obsidian tokens + Bootstrap utility overrides |
| `app/static/css/responsive-financial.css` | Color adjustments for dark theme |
| `app/static/css/mobile.css` | **DELETE** — dead code (not loaded by any template) |
| `app/templates/index.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/stocks.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/analysis.html` | Remove emoji, remove purple gradient inline styles |
| `app/templates/screen.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/backtest.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/stock_detail.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/ml_factor/index.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/ml_factor/analysis.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/ml_factor/backtest.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/ml_factor/models.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/ml_factor/portfolio.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/ml_factor/scoring.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/text2sql/index.html` | Convert to extend base.html, remove standalone navbar/styles, replace JS-generated Bootstrap classes |
| `app/templates/realtime_analysis/index.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/realtime_analysis/indicators.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/realtime_analysis/monitor.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/realtime_analysis/report_management.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/realtime_analysis/risk_management.html` | Remove emoji, remove light-theme status color inline styles |
| `app/templates/realtime_analysis/signals.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/realtime_analysis/websocket_management.html` | Remove emoji, remove light-theme inline styles |
| `app/templates/data_management/index.html` | Remove emoji, remove purple gradient inline styles, replace status color classes |

### Not Modified (explicit)

| File | Reason |
|------|--------|
| `app/templates/api_test.html` | Developer debug page, left as-is |

## Data Flow

No data flow changes. All JavaScript functions, endpoint URLs, request bodies, and rendered table data remain unchanged.

## Error Handling

Alert components are restyled to use tinted dark backgrounds with colored left borders. Functional behavior unchanged.

## Testing

- Start the app locally with `python run.py`
- Manually verify all major pages render correctly in the new theme
- Check navbar, hero banner, cards, tables, forms, buttons, modals, alerts on:
  - Homepage (`/`)
  - Stock list (`/stocks`)
  - ML Factor pages (`/ml-factor/*`)
  - Realtime analysis pages (`/realtime-analysis/*`)
- Run `pytest -q` to confirm no template or route regressions

## Risks

- **Global CSS rewrite**: Touching `financial-theme.css` affects all pages. Mitigate by thorough visual testing across all page types. **Rollback strategy**: work on a git branch; revert by switching branches if issues arise.
- **Bootstrap utility class overrides**: Using `!important` to override `bg-primary`, `bg-success`, etc. may conflict with Bootstrap's own `!important` usage. Mitigate by testing all pages that use these classes in JS-generated HTML (text2sql, models, monitor, websocket_management, analysis, indicators).
- **text2sql conversion**: Converting from standalone to extending `base.html` is a structural change. If the conversion breaks, the page may lose functionality. Mitigate by testing the text2sql query flow end-to-end.
- **ECharts theme**: Charts on analysis pages must be verified — the theme registration only affects new chart instances; existing hardcoded colors in page JS may need updating.
- **Mobile responsiveness**: Dark theme must be tested on mobile viewports. The responsive CSS needs color updates, not structural changes.
- **Emoji in JS strings**: Some templates embed emoji in JavaScript template literals (e.g., loading messages, error text). Only remove emoji from HTML heading elements — leave JS string content unchanged.
