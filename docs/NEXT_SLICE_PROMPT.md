# Next Implementation Slice — Public Map D.5 (context window brief)

_Generated 2026-05-09. Hand this file to the next Claude session as the opening message._

---

## What this project is

A local-first Python/Streamlit/SQLite dashboard (`/home/user/GovJobs`) with a companion public map
(`public_map/` — SvelteKit + Mapbox GL JS, deployed to Cloudflare Pages at `thegrandpipeline.com/map`).
The map is fed by nightly static-JSON snapshots exported by `scripts/export_public_map.py`. There is
no public server, no FastAPI, no user accounts. The dashboard user is the sole operator.

Source of truth for the project: `CLAUDE.md` (root). Source of truth for the map: `docs/MAP_FEATURE_SPEC.md`
and `docs/ROADMAP.md` (D.5 section). Source of truth for decisions: `docs/DECISIONS.md`.

---

## Current git state

- Working branch: `claude/public-map-next-slice-LQcrr`  
- All work in this session lives on that branch; push there when done.
- `public_map/` builds cleanly with `npm run build` (verified 2026-05-09).

---

## What is already shipped (D.5)

| Phase | Status | Summary |
|---|---|---|
| D.5.-1 | ✅ | Self-bootstrapping ingest pipeline (`ingest_common.py`) |
| D.5.2 | ✅ | Agency multi-select with code-backed chips |
| D.5.3 | ✅ | Saved searches in localStorage |
| D.5.4 | ✅ | Address/ZIP geocoder (Mapbox → Nominatim → offline ZIP centroids) |
| D.5.5 | ⚠️ partial | Click polygon → fit bounds + Back-to-national pill. **Missing: scoped action window (D.5.15).** |
| D.5.6 | ✅ | Metric status field + auto-demotion in MetricSwitcher |
| D.5.7 | ⚠️ partial | Corpus-growth infra exists; DB only has ~34 open jobs. Needs operator import run. |
| D.5.13 | ⚠️ partial | `InfoTooltip.svelte` wired in StateRoundup. **Missing: LocalityDetail, CountyDetail, JobCard pay grid.** |
| D.5.18 | ✅ | Urgency badges (close date driven) in JobCard and JobList |
| D.5.19 | ✅ | Local profile: viewed/saved/hidden, ProfileDrawer, mapState.hiddenJobIds → excludeHidden() |
| D.5.20 | ✅ | Public Map Admin: one-click refresh + federal-wide import control |

**Not started:** D.5.0 (breakpoint tests), D.5.1 (heat visual verify), D.5.8 (OSM hardening),
D.5.9 (federal property layer), D.5.10 (county COL), D.5.11 (exact pay tables),
D.5.14 (2026 GS tables), D.5.15 (scoped search windows), D.5.16 (light/dark mode),
D.5.17 (compensation comparator), D.5.21 (job history window), D.5.22 (timeline chart),
D.5.23 (quick-add filter chips), D.5.12 (verification pass).

---

## Key file map (read these before touching anything)

```
public_map/src/
  lib/
    Map.svelte            — map init, layer management, click routing, filter $effects
    store.svelte.ts       — all reactive mapState (metric, filters, hiddenJobIds, demotedMetrics, …)
    filters.ts            — JobFilters interface + filterJobs() pipeline
    FilterPanel.svelte    — left-side filter drawer; updateFilters() is the canonical write path
    JobCard.svelte        — job detail panel (loads detail + pay tables; Save/Hide/urgency)
    JobList.svelte        — scoped job list for state/locality polygon clicks
    MetricSwitcher.svelte — bottom-center choropleth picker; status-aware (wip/ready/experimental)
    metrics.ts            — MetricDef type, METRICS record, fillColorExpression
    format.ts             — urgencyBadge, money, salaryRange, gradeRange helpers
    jobProfile.svelte.ts  — localStorage singleton for viewed/saved/hidden jobs
    ProfileDrawer.svelte  — right-side drawer: Saved / Hidden / Viewed-Closed tabs
    data.ts               — loadJobs, loadStates, loadJobDetailsIndex, loadPayTables, …
    layers.ts             — SOURCE_IDS, LAYER_IDS, addAllLayers, setStateFillMetric
    layout.ts             — LAYOUT_SLOTS enum; every component must declare its slot
    InfoTooltip.svelte    — reusable ⓘ hover tooltip for calculation tracebacks
    StateRoundup.svelte   — state-click feature panel (uses InfoTooltip)
    LocalityDetail.svelte — locality-click feature panel
    basemap.ts            — Mapbox / OSM fallback style selection
  routes/map/+page.svelte — root map page: mounts all components, masthead, profile button

src/public_map_export.py  — Python export pipeline; writes static/data/*.json + *.geojson
scripts/export_public_map.py — CLI entry point for the export
public_map/static/data/   — exported bundle (jobs.geojson, states.geojson, manifest.json, …)
```

---

## Recommended next slice

Implement **D.5.23 → D.5.15 → D.5.16** in that order. They are independent enough to parallelize
reading but must be committed sequentially. Together they close the "UX completeness" gap that
makes the map feel unfinished to a first-time visitor.

### D.5.23 — Quick-add filter chips

**Goal:** Every displayed job attribute that maps to a filterable field gets a small `+` button
(visible on hover/focus). Clicking it adds that value as a filter chip without closing the card.

**Design rules:**
- Create `QuickAdd.svelte`: a micro-component that wraps any value string.  
  Props: `value: string`, `label: string`, `onAdd: () => void`.  
  Renders the value followed by a `+` button (12 px, appears on `li:hover` / focus-within).
- `onAdd` must call the **same `updateFilters` path used by FilterPanel.svelte** — do not invent
  a second write path for filter state. Check how FilterPanel currently mutates `mapState.filters`
  and replicate that pattern exactly.
- Wire into:
  - `JobCard.svelte` — agency (→ agencies chip), series (→ series), grade_low/grade_high (→ gradeMin/gradeMax), state (→ geo scope chip), locality_code (→ locality scope once D.5.15 exists; for now skip), remote_status (→ remote toggle if value is 'remote' or 'hybrid'), pay_plan (→ payPlan).
  - `JobList.svelte` rows — same fields as JobCard for visible row cells.
  - `StateRoundup.svelte` — state name → geo scope chip.
  - `LocalityDetail.svelte` — locality code → locality scope chip (once D.5.15 wires geography chips).
- For geo scope chips (state, locality): if `mapState.filters` does not yet have a `geoScopes` field,
  add it to `JobFilters` in `filters.ts` as `geoScopes: string[]` (starts empty) and filter jobs
  accordingly (keep as an OR across scopes, ANDed with other filters). This lays the foundation for D.5.15.
- `QuickAdd.svelte` must be in `public_map/src/lib/layout.ts` grid slot `'inline'` (add this slot).

### D.5.15 — Snap-scoped geographic search windows

**Goal:** Clicking a state, locality, county, or CBSA polygon fits the map to its bounds (already
done via `fitFocusedFeature`) AND opens a compact "scoped action window" in the FeaturePanel area
that offers:
1. **Search this area** — sets a single geo-scope chip and clears other geo chips.
2. **Add to Search** — appends a geo-scope chip to existing chips (ORed with others).
3. **Include remote** — adds the current geo chips AND sets remote filter to 'remote'.
4. **Preview: with global filters / without** — toggles a transient `previewIgnoreGlobal` flag
   that temporarily shows unfiltered counts in the scope window without mutating `mapState.filters`.

**Implementation notes:**
- The scoped window renders inside `FeaturePanel.svelte` as a new view type alongside JobCard/JobList.
  Add a `ScopedSearchWindow.svelte` component.
- `mapState` needs `geoScopes: string[]` (already being added by D.5.23).
- `filterJobs` in `filters.ts` must honor `geoScopes`: if non-empty, include only jobs whose
  `state` or `locality_code` matches any entry in the array (OR logic).
- The polygon click handler in `Map.svelte` already calls `fitFocusedFeature` — after that, set
  `mapState.selectedFeature` to a new type `{source: 'scope', label, code, scopeType: 'state'|'locality'|'county'|'cbsa', properties}`.
  `FeaturePanel.svelte` routes this to `ScopedSearchWindow.svelte`.
- The "Back to national" pill should clear `mapState.focusedArea` AND remove geo scope chips
  that match the cleared area.
- Job count in the scoped window is `filterJobs(allJobs, filters, details).features.filter(inScope)`.

### D.5.16 — Light/dark mode toggle

**Goal:** A light/dark toggle button (sun/moon icon) in the masthead persists the user's
preference in localStorage (`tgp.public_map.theme.v1`: `'light'|'dark'`) and applies the
theme to panels, controls, overlays, and the basemap style.

**Implementation notes:**
- Create `theme.svelte.ts` alongside `jobProfile.svelte.ts`:
  ```ts
  class Theme {
    current = $state<'light'|'dark'>(loadTheme());
    toggle() { this.current = this.current === 'dark' ? 'light' : 'dark'; saveTheme(this.current); }
  }
  export const theme = new Theme();
  ```
- Apply via a `data-theme="dark"|"light"` attribute on `<html>` or the `.root` div.
- All dark-mode color values currently hardcoded in component `<style>` blocks must move to CSS
  custom properties in a single root stylesheet (`public_map/src/app.css` or a new
  `public_map/src/lib/theme.css`). Light mode provides the same set of variables.
  At minimum: `--bg-panel`, `--border-panel`, `--text-primary`, `--text-muted`, `--accent`,
  `--pill-bg`, `--pill-border`.
- Basemap: dark mode uses `pickStyle()` (Mapbox dark / OSM dark); light mode switches to a
  light Mapbox style or OSM standard tiles. If swapping map styles mid-session is expensive,
  use a map style reload (`map.setStyle(newStyle)`) and re-add all sources/layers in the
  existing `addAllLayers` path.
- Toggle button sits in the masthead (right of the "My Jobs" pill), slot `masthead` in `layout.ts`.
- Must pass the no-overlap invariant: light-mode panels must not be unreadable on a light basemap.

---

## The three new plan items (already added to ROADMAP.md)

### D.5.21 — Per-job historical postings window

Each JobCard gets a "History" tab. When opened:

**Backend** (`src/public_map_export.py`):
- New function `job_history_payload(conn) → dict` — queries the `jobs` table for all rows
  that share the same `position_id` as any job in the current `jobs.geojson` export.
  Returns a dict keyed by `position_id`, each entry an array of:
  ```json
  { "id": 123, "open_date": "2024-03-01", "close_date": "2024-03-22",
    "salary_min": 85000, "salary_max": 110000, "state": "DC", "source": "historicjoa" }
  ```
  Only include entries where `source IN ('historicjoa', 'usajobs')`.
  Cap at 20 entries per position_id (most recent first).
- Also emit a "similar" second tier: jobs with the same `agency_code + series + grade_low`
  that do NOT share `position_id`. Cap at 10 entries per job, deduplicated by position_id.
- `scripts/export_public_map.py` writes `job_history.json`.

**Frontend** (`public_map/src/lib/`):
- `data.ts`: add `loadJobHistory(): Promise<Record<string, HistoryEntry[]>>` (lazy, cached).
- `JobCard.svelte`: add a "History" tab toggle below the title. On first open, call
  `loadJobHistory()`, look up `properties.position_id`, render a compact list.
- If the position has no history rows, show: "No prior postings found for this position ID."
- If similar postings exist, show them in a second section "Similar postings (same agency/series/grade)."
- Trend label: compute from history array — "Posted N times in the last 24 months."
- No LLM. Matching is purely `position_id` equality and `agency_code + series + grade_low` equality.

### D.5.22 — Posting timeline chart (filter-scoped)

A collapsible sparkline panel showing monthly posting counts for the active filter set.

**Backend** (`src/public_map_export.py`):
- New function `timeline_payload(conn) → dict`. Queries `jobs` where
  `source IN ('historicjoa', 'usajobs') AND open_date IS NOT NULL`.
  Returns:
  ```json
  {
    "months": ["2024-01", "2024-02", ...],   // trailing 24 months, ISO YYYY-MM
    "total": [12, 18, ...],                  // total postings per month
    "by_agency": { "HSCB": [2, 3, ...], ... },  // top-20 agencies
    "by_series": { "0343": [1, 2, ...], ... },  // top-20 series
    "by_state":  { "DC": [5, 6, ...], ... }     // all states
  }
  ```
  The client ORs/ANDs slices client-side to approximate the active filter. This is an
  approximation — not exact SQL — because the export is static. Label it "approximate" in the UI.
- `scripts/export_public_map.py` writes `timeline.json`.

**Frontend**:
- `TimelineChart.svelte`: renders a plain SVG bar chart (no chart library). Width fills its
  container; height fixed at 80 px. Bars colored with the active metric's accent color.
  X-axis: month labels every 3 months. Y-axis: auto-scale.
- `data.ts`: `loadTimeline(): Promise<TimelineData>` (lazy, cached).
- Panel: a collapsible row above the MetricSwitcher (same slot `metric` but stacked).
  Toggle button: "📈 Posting trend" or a text "Trend ▾/▴".
- The chart recomputes whenever `mapState.filters` changes using the precomputed slices.
  If the active filter matches no precomputed slice (e.g. keyword filter), the chart
  falls back to `total` and shows a note: "Keyword filter active — showing unfiltered trend."
- No bar-click zoom in V1; that's V2.

### D.5.23 — Quick-add filter chips (already in recommended next slice above)

---

## Invariants — never break these

1. No component uses `position: absolute` outside of a declared `layout.ts` slot.
2. `filterJobs()` in `filters.ts` is the only place that evaluates filter logic; don't add a second.
3. `jobProfile.svelte.ts` is the only place that reads/writes localStorage profile state.
4. `mapState` in `store.svelte.ts` is the only reactive global; no component-local state
   that duplicates it.
5. The map hard-caps at `maxZoom: 9`. No street-level views.
6. Closed postings from `closed_jobs.geojson` are never shown as "apply" targets.
7. The exporter (`src/public_map_export.py`) writes all bundle files; the frontend only reads.
8. `npm run check` must return 0 errors before any commit.
9. `npm run build` must succeed before pushing.

---

## Starting the session

```bash
cd /home/user/GovJobs
git checkout claude/public-map-next-slice-LQcrr
cd public_map
npm run check   # verify clean baseline
```

Read these files before writing any code:
- `public_map/src/lib/filters.ts` — understand the full JobFilters interface and filterJobs pipeline
- `public_map/src/lib/FilterPanel.svelte` — understand the existing chip add/remove pattern
- `public_map/src/lib/store.svelte.ts` — full reactive state shape
- `public_map/src/lib/JobCard.svelte` — current card structure
- `public_map/src/lib/Map.svelte` (lines 60–160) — filter $effect and excludeHidden pattern

Implement D.5.23, then D.5.15, then D.5.16 in that order. Run `npm run check` after each.
Mark items `[x]` in `docs/ROADMAP.md` when shipped. Update `CLAUDE.md` current-architecture
bullet for each shipped phase. Commit per phase with a descriptive message. Push to
`claude/public-map-next-slice-LQcrr` when done.
