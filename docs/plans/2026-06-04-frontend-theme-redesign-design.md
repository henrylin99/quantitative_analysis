# Frontend Theme Redesign Design

Date: 2026-06-04

## Context

The current Flask/Jinja frontend uses Bootstrap 5, Font Awesome, `base.html`, and shared CSS in `app/static/css/financial-theme.css` and `app/static/css/responsive-financial.css`. The ML factor pages inherit this shared theme and add dense workflows for scoring and portfolio management.

The main visual issues are:

- Buttons and typography feel too large and heavy for a repeated-use financial tool.
- The dark color scheme only partially updates surfaces, leaving body text, muted text, inputs, tables, modals, and other elements with weak contrast.
- Several theme effects, such as strong gradients, hover movement, and large card spacing, make the UI feel rough instead of calm and operational.

## Goals

- Make the whole app feel like a quiet, dense, readable financial dashboard.
- Fix dark-mode contrast across shared components, especially muted text against dark surfaces.
- Reduce button, heading, card, and table scale without making touch targets unusable.
- Apply light ML factor page refinements for the scoring and portfolio workflows.
- Keep the change scoped to presentation; do not change API behavior or business logic.

## Non-Goals

- Rebuild the entire design system or replace Bootstrap.
- Redesign navigation structure or page information architecture.
- Add a manual theme switcher.
- Rewrite charts, data flows, or backend endpoints.

## Recommended Approach

Use a shared theme pass plus ML factor page refinements.

The shared pass should define clearer visual tokens for light and dark modes, then apply them to Bootstrap primitives such as body, cards, buttons, forms, tables, dropdowns, modals, alerts, badges, and muted text. This fixes the root contrast and scale problems for all pages that inherit `base.html`.

The ML factor pass should be small and targeted: tune page headers, form rows, card spacing, and table action buttons so scoring and portfolio screens read as compact tools instead of oversized content pages.

## Alternatives Considered

### Minimal Token Patch

Only adjust dark-mode colors and button sizes. This is fastest and lowest risk, but leaves page-level roughness, oversized headings, and inconsistent dense-table actions.

### Full Design System Rewrite

Rebuild the theme around a new component layer. This could produce the most polished result, but it would touch too many templates and create unnecessary regression risk for this request.

## Visual Direction

The visual direction is restrained and operational:

- Body text near 14px.
- Page titles around 24-28px.
- Card titles around 15-16px.
- Tables around 13-14px.
- Button font weight around 500.
- Standard buttons around 32-36px high.
- Icon-only row actions remain compact, with clearer hover and focus states.
- Gradients and hover lift effects are reduced so the app feels steadier.

Cards should stay readable but less bulky. Dense workflow pages should prioritize scanning, comparison, and repeated action.

## Dark Mode Design

Dark mode should use a complete set of readable tokens:

- Page background.
- Elevated surfaces.
- Card and modal backgrounds.
- Borders and dividers.
- Primary text.
- Secondary and muted text.
- Input backgrounds and placeholders.
- Table headers, rows, and hover states.
- Dropdown menus.
- Alerts and badges.

The most important fix is making `.text-muted`, table text, form controls, and card bodies clearly legible against dark surfaces.

## Component Scope

Shared component refinements:

- `body`
- `.main-content`
- `.navbar-financial`
- `.card` and `.card-financial`
- `.card-header` and `.card-body`
- `.btn`, `.btn-sm`, outline buttons, and financial button variants
- `.form-control`, `.form-select`, labels, placeholders, and help text
- `.table`, table headers, table hover states, and `.table-responsive`
- `.dropdown-menu` and `.dropdown-item`
- `.modal-content`, `.modal-header`, `.modal-footer`
- `.alert`, `.badge`, `.text-muted`

ML factor page refinements:

- `app/templates/ml_factor/scoring.html`
- `app/templates/ml_factor/portfolio.html`

These pages should receive lightweight class hooks or existing Bootstrap utility adjustments where shared CSS alone cannot produce the intended density.

## Data Flow

No data flow changes are required. Existing JavaScript functions, endpoint URLs, request bodies, and rendered table data should remain unchanged.

## Error Handling

Existing error rendering should remain functionally unchanged. The visual layer should make alert backgrounds and text readable in both light and dark modes.

## Testing

Verification should include:

- Run the app locally.
- Open the scoring and portfolio pages.
- Check light and system dark mode rendering.
- Verify buttons, inputs, tables, modals, dropdowns, alerts, and muted text are readable.
- Use browser screenshots or Playwright where practical to catch obvious layout and contrast regressions.
- Run any existing frontend-adjacent or template tests if available.

## Risks

- Global CSS changes can affect unrelated pages. Mitigate by using conservative Bootstrap-compatible overrides.
- Dark mode depends on `prefers-color-scheme`; visual checks should cover both color schemes.
- Some generated HTML inside page scripts uses Bootstrap classes directly, so shared class coverage matters more than template-only edits.
