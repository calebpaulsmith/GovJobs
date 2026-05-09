# Next Slice Context Brief — 2026-05-09

Ready-to-paste context for the next session. Target slice: **D.5.23 → D.5.15 → D.5.16**.

---

## Recommended order

1. **D.5.23** — Quick-add filter chips (`QuickAdd.svelte`)
2. **D.5.15** — Snap-scoped geographic search windows
3. **D.5.16** — Light/dark mode toggle

Rationale: D.5.23 is purely additive (no new state, no new exports), so it de-risks the session. D.5.15 builds on the polygon-click / fit-bounds foundation from D.5.5 (partially shipped). D.5.16 is a styling pass that touches every component — do it last so it doesn't conflict with new markup from D.5.23 and D.5.15.

---

## Current branch state (as of 2026-05-09)

Working branch: `claude/add-roadmap-items-nC4kq`  
Base: `main` (last merge: PR #7, `claude/public-map-next-slice-LQcrr`)

Shipped this session: D.5.2, D.5.3, D.5.4, D.5.6, D.5.18, D.5.19, D.5.20, D.5.-1  
Partially shipped: D.5.0, D.5.1, D.5.5, D.5.7, D.5.13

---

## Key file locations

### Public map frontend (`public_map/src/lib/`)

| File | Relevance |
|------|-----------|
| `store.svelte.ts` | `mapState` singleton — `mapState.filters: JobFilters` is the single source of truth for all active filters |
| `filters.ts` | `JobFilters` interface, `DEFAULT_FILTERS`, `filterJobs()`, `activeFilterCount()` |
| `FilterPanel.svelte` | Has a local `setFilter<K>(key, value)` helper that writes to `mapState.filters` and triggers URL state sync — **QuickAdd must call the same path** |
| `JobCard.svelte` | Job detail card; mount-marks viewed; has Save/Hide buttons; target for quick-add and History tab |
| `JobList.svelte` | Row list; target for quick-add chips |
| `StateRoundup.svelte` | State detail panel; target for quick-add chips on agency/series values |
| `LocalityDetail.svelte` | Locality detail panel; target for quick-add chips |
| `Map.svelte` | Polygon click handler; `computeMetricDemotion`; `setChoroplethVisible`; fit-bounds logic initiated in D.5.5 |
| `FeaturePanel.svelte` | Right-side panel host; renders `StateRoundup`, `LocalityDetail`, `CountyDetail`, or `JobList` |
| `MetricSwitcher.svelte` | Bottom-center metric pills; target for timeline sparkline (D.5.22) above it |
| `layout.ts` | Grid cell declarations — every new component must declare its cell here |
| `layers.ts` | Layer order and zoom constraints; address-pin layer lives here |
| `InfoTooltip.svelte` | Reusable ⓘ hover/focus/click tooltip — reuse before adding any new tooltip pattern |

### Export / backend

| File | Relevance |
|------|-----------|
| `src/public_map_export.py` | Writes all static JSON/GeoJSON; add `job_history.json` (D.5.21) and `timeline.json` (D.5.22) here |
| `scripts/export_public_map.py` | Orchestrator that calls export functions; wire new outputs here |
| `src/database.py` | Schema; schema version is 10 after zip_centroids |

---

## D.5.23 — Quick-add filter chips

**What to build:** `QuickAdd.svelte` — a micro-component that wraps any displayed value with a `+` button on hover. Clicking it appends the value to the appropriate `mapState.filters` key.

**Design rules:**
- Must call `mapState.filters.<key> = newValue` (or the equivalent reactive assignment) — the same write path `FilterPanel`'s `setFilter` uses. Do **not** introduce a second write path.
- The `+` button is only shown on `hover` / `focus-within` of the host element (CSS `:hover` on a wrapper `<span>` is fine).
- Supported chip types and their filter keys:
  - `agency` code → `mapState.filters.agencies` (push if not already present)
  - `series` → `mapState.filters.series` (replace; series is a single string)
  - `grade` → `mapState.filters.gradeMin` (set if empty, otherwise leave)
  - `payPlan` → `mapState.filters.payPlan` (replace)
  - `hiringPath` → `mapState.filters.hiringPath` (replace)
- The component takes `{ type: 'agency'|'series'|'grade'|'payPlan'|'hiringPath', value: string, label?: string }` as props.
- Wire it into: `JobCard` (agency, series, grade, payPlan, hiringPath), `JobList` rows (agency, series), `StateRoundup` (agency), `LocalityDetail` (agency).
- `FilterPanel` must not be duplicated — just import `mapState` and mutate directly.

**Invariant from CLAUDE.md:** `mapState.filters` is the single source of truth; no second write path.

---

## D.5.15 — Snap-scoped geographic search windows

**What to build:** When a user clicks a state or locality polygon, the map fits bounds to that polygon (D.5.5, partially done) **and** opens a compact scoped action window.

**Scoped window contents (per ADR-0028 and CLAUDE.md invariant #16):**
- Header: polygon name + layer type (State / Locality)
- `Search this area` button — sets a `geography` chip in filters
- `Include remote` toggle — whether remote-only jobs are included
- `Add to Search` button — adds a geography chip without replacing existing filters (invariant #17: multiple geography chips are ORed, ANDed with other filters)
- Filter preview toggle: show job count **with** global filters applied vs. **without** (count derived client-side from `filterJobs(allJobs, mapState.filters, details)`)

**Geography chip support needed in `filters.ts`:**
- Add `geographies: string[]` to `JobFilters` (list of state FIPS or locality codes).
- `filterJobs` should AND geography chips: a job passes if its `state_fips` or `locality_code` matches any of the geography codes.
- URL state: repeated `geo=` keys, same pattern as `agency=`.

**Fit-bounds:** D.5.5 initiated `Map.svelte` polygon click → compute bounds → `fitBounds`. Verify this path works, then add the scoped window as an overlay.

**Layout cell:** `scoped-window` — top-center below masthead or floating near the clicked polygon (decide and declare in `layout.ts`). Must not overlap `FeaturePanel` on the right.

---

## D.5.16 — Light/dark mode toggle

**What to build:** A visible light/dark toggle in the masthead or top-right area. Persists to `localStorage` key `tgp.public_map.theme.v1`.

**Scope:**
- CSS custom properties (variables) for all panel backgrounds, text, border, and overlay colors.
- Two Mapbox basemap styles: light (current) and dark (use `mapbox://styles/mapbox/dark-v11` with Mapbox token; OSM dark tile layer without token).
- The toggle changes `document.documentElement.dataset.theme` (`'light'|'dark'`); all CSS selectors use `[data-theme='dark']` overrides.
- Apply to: masthead, FilterPanel, FeaturePanel, MetricSwitcher, InfoTooltip, ProfileDrawer, SavedSearchMenu, AddressSearch, scoped window (D.5.15).
- Must pass legibility: minimum contrast ratio 4.5:1 for body text in both modes.
- `layout.ts` grid cell: `theme-toggle` — declare it before placing the DOM node.

**State:** add `theme: 'light' | 'dark'` to `mapState` in `store.svelte.ts`; initialize from `localStorage`; persist on change. Map.svelte watches `mapState.theme` and swaps the basemap style.

---

## Invariants to preserve (from CLAUDE.md)

1. `mapState.filters` is the **only** write path for filter state. QuickAdd, scoped window, and any other new component must import `mapState` and mutate it directly — never maintain a parallel copy.
2. Every new UI component must declare its `layout.ts` grid cell before being placed in the DOM.
3. `InfoTooltip.svelte` is the canonical tooltip component — reuse it, do not create new tooltip patterns.
4. `filterJobs(allJobs, mapState.filters, details)` is the canonical filter pipeline — it must see geography chips from D.5.15 so heat, markers, and list counts stay consistent.
5. No element overlap — the scoped window from D.5.15 and the FeaturePanel must coexist without covering each other at any of the three breakpoints (≥ 1200 px, 720–1199 px, < 720 px).
6. OSM fallback must keep working — D.5.16 dark mode must supply a no-token dark tile layer (OSM Carto dark or similar) and must not introduce any `glyphs:` URLs that require Mapbox auth.

---

## Tests to write alongside each feature

- **D.5.23:** unit-test `QuickAdd` — clicking `+` on an agency value appends to `mapState.filters.agencies`; clicking `+` on a series value sets `mapState.filters.series`; already-present agency is not duplicated.
- **D.5.15:** unit-test geography chip — `filterJobs` with `geographies: ['06']` returns only CA jobs; `filterJobs` with `geographies: ['06', '48']` returns CA + TX jobs; empty `geographies` returns all jobs.
- **D.5.16:** smoke-test that `mapState.theme = 'dark'` does not throw; localStorage round-trip preserves the value.

---

## What NOT to do this session

- Do not implement D.5.21 (job history tab) or D.5.22 (timeline sparkline) — those require backend export changes.
- Do not start D.5.12 (verification pass) until D.5.23, D.5.15, and D.5.16 are complete.
- Do not add a new filter write path — only extend `mapState.filters` via the existing mechanism.
