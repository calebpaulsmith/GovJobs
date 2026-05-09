# Next Slice Context Brief — 2026-05-09

Ready-to-paste context for the next session. Target slice: **D.5.25 → D.5.26**. Both are listed in `docs/ROADMAP.md` under Phase D.5.

---

## Recommended order

1. **D.5.25** — Geographic detail card hierarchy parity (NationalRoundup card + ScopedAreaActions on CountyDetail).
2. **D.5.26** — County as a first-class geography filter chip.

Rationale: D.5.25 is additive UI plumbing (one new component + wiring an existing one into a third detail card). D.5.26 depends on D.5.25's `ScopedAreaActions` being live on CountyDetail and on `county_fips` being present on job markers — do D.5.25 first so D.5.26 can lean on it.

The two together close the loop opened by D.5.10 (county-level COL data is now exported and rendered, but counties still aren't drillable as a geography chip and there's no national overview to anchor comparisons).

---

## Current branch state (as of 2026-05-09)

Last merged into `master`: PR #10 (`claude/start-next-slice-ZILbs`) — D.5.14 + D.5.11.
Just shipped on `claude/start-next-slice-ERH1S` (commit `603f417`): **D.5.10** — county COL via ACS rent + BEA state RPP. ADR-0031 added.

Open D.5 items after this slice would be: D.5.0, D.5.1, D.5.5 (visual verification), D.5.7, D.5.9, D.5.14 operator step, D.5.17, D.5.24, D.5.12.

---

## Key file locations

### Public map frontend (`public_map/src/lib/`)

| File | Relevance |
|------|-----------|
| `store.svelte.ts` | `mapState` singleton — `mapState.filters: JobFilters` is the single source of truth. `mapState.selectedFeature` carries the active polygon click. `mapState.focusedArea` was set in D.5.5 for the Back-to-national pill. |
| `filters.ts` | `JobFilters` already has `geographies: string[]` from D.5.15. Add `county:<fips>` support to `filterJobs`. URL state already round-trips repeated `geo=` keys. |
| `FilterPanel.svelte` | Chip rendering for active geographies — extend to label county chips with the county name (lookup from `counties.geojson`). |
| `FeaturePanel.svelte` | Right-side panel host. Renders `StateRoundup`, `LocalityDetail`, `CountyDetail`, or `JobList` today. Add a `NationalRoundup` branch as the default when nothing is selected. |
| `StateRoundup.svelte` | Reference for what the national card should look like. |
| `LocalityDetail.svelte` | Already wires `ScopedAreaActions`. Reference for how CountyDetail should wire it. |
| `CountyDetail.svelte` | Just enriched in D.5.10 with median rent + County COL index + InfoTooltips. Targets for: `ScopedAreaActions` block, county-level QuickAdd chip. |
| `ScopedAreaActions.svelte` | Used today by State/Locality. Accepts a `scope` prop with `{ kind, code, label }`. Must also handle `kind: 'county'`. |
| `QuickAdd.svelte` | Already supports a `geography` chip type. Wire it into CountyDetail (county FIPS → county chip) and JobCard's clicked-location row. |
| `Map.svelte` | Polygon click handler already fits county bounds (D.5.5). On county click, set `mapState.selectedFeature` so the panel opens; same as State/Locality. |
| `layout.ts` | NationalRoundup reuses the existing `feature-panel` cell. No new cell needed. |

### Export / backend (`src/public_map_export.py`, `scripts/`)

| File | Relevance |
|------|-----------|
| `_feature_from_marker` (line ~141) | **Add `county_fips` to the returned `properties`.** The marker dataset already carries it (line ~85, `city_lookup.county_fips AS county_fips`). One-line change in `_feature_from_marker`; pass-through in `recently_closed_features` too. |
| `job_details` (line ~403) | Inspect the per-job locations payload — make sure `county_fips` is in `detail.locations[]` for the JobCard's clicked-location row to render a county QuickAdd. |
| `manifest.json` | No new fields needed; existing `layers` and `data_sources` map keeps reflecting reality. |
| `agency_options` / `series_options` | Reference for how a "top N agencies" list could be rendered in NationalRoundup. National card can read existing `agencies.json` + `manifest.json` rather than introducing a new export. |

---

## D.5.25 — NationalRoundup + ScopedAreaActions on CountyDetail

**`NationalRoundup.svelte`** — new component, layout cell `feature-panel`. Default content of `FeaturePanel` when `mapState.selectedFeature` and `mapState.listView` are both null. Sections:

- **Headline metrics row.** Total open postings (sum of all jobs.geojson features), total federal workforce / accessions / separations from `opm_state_aggregates`, median state RPP from `cost_of_living.by_state`, median GS-13 step 1 across localities (compute client-side from `pay_tables.json`).
- **Top 5 agencies by openings.** Reads `agencies.json` (already produced by `agency_options`); render with QuickAdd chips so a click adds the agency to the filter.
- **Top 5 states by openings.** Reads `states.geojson` features; QuickAdd chips with `geography` kind.
- **National pay-vs-COL caption.** Sentence summarizing the spread (e.g., "GS-13 step 1 ranges from $X (RUS) to $Y (SF) in 2026; purchasing-power index 84–112"). Read `pay_tables.json` + `cost_of_living.json`.
- **InfoTooltip on every computed value** with the formula and source — reuse `InfoTooltip.svelte` per the existing invariant.

The "Back to national" pill in `Map.svelte` should both clear focus (existing) and force `mapState.selectedFeature = null` so the panel renders NationalRoundup. No new state needed; FeaturePanel already short-circuits to "default" when nothing is selected — replace that with `<NationalRoundup />`.

**`ScopedAreaActions` on CountyDetail.** Mount the existing component at the top of `CountyDetail.svelte` with:

```svelte
<ScopedAreaActions
  scope={{ kind: 'county', code: properties.fips, label: `${properties.name} County, ${properties.state}` }}
  filteredCount={...}
  totalCount={...}
/>
```

Filtered/total counts come from `filterJobs(allJobs, mapState.filters, details)` and `filterJobs(allJobs, defaultFilters, details)` so the with/without-global-filter preview keeps working (per CLAUDE.md invariant 16/17). The component's "Search this area" / "Add to search" / "Remove" buttons must call the same `mapState.filters.geographies` path State and Locality use — no parallel write path.

**Tests for D.5.25:**

- `NationalRoundup.svelte` mounts with a synthetic `mapState` and renders the four headline values.
- FeaturePanel renders NationalRoundup when `selectedFeature` is null.
- ScopedAreaActions on a county scope dispatches a `county:<fips>` chip through `mapState.filters.geographies`. (Failing until D.5.26 lands the chip parsing — write the test now and let it skip until D.5.26 unlocks it, or stage it as a single PR.)

---

## D.5.26 — County as a first-class geography filter chip

**Backend (one-line surface change):**

In `src/public_map_export.py::_feature_from_marker` add `"county_fips": marker.get("county_fips"),` to the returned properties. The data is already in `_marker_dataset`'s SELECT (line 85). Closed-jobs path uses the same helper. Add `county_fips` to whatever `detail.locations[]` shape `job_details` produces if it isn't there yet — verify in code.

**Frontend filter wiring (`public_map/src/lib/filters.ts`):**

`JobFilters.geographies` already exists. Extend `filterJobs` so a chip prefixed `county:` matches a job whose marker `county_fips` (or any of `detail.locations[].county_fips`) equals the chip code. Pseudocode:

```ts
function passesGeography(job, geographies, details) {
  if (geographies.length === 0) return true;
  const detail = details[job.id];
  return geographies.some(chip => {
    const [kind, code] = chip.split(':');
    if (kind === 'state') return job.state === code;
    if (kind === 'locality') return job.locality_code === code;
    if (kind === 'county') {
      if (job.county_fips === code) return true;
      return (detail?.locations ?? []).some(l => l.county_fips === code);
    }
    return false;
  });
}
```

URL state needs nothing new — `geo=county:17031` repeats just like the state/locality keys.

**FilterPanel chip labels:** when rendering an active `county:<fips>` chip, look up the county name from `counties.geojson` features (cache the FIPS → name map in a derived store). Display "Cook County, IL ×" instead of "county:17031 ×".

**QuickAdd integration:** `QuickAdd.svelte` already supports `geography`. Add its `+` button next to:
- The county name in `CountyDetail.svelte` header.
- The `county_fips` value (when present) in JobCard's clicked-location row inside `JobCard.svelte`.

**Tests for D.5.26:**

- `filterJobs` unit test — `geographies: ['county:17031']` keeps Cook County jobs and drops everything else; `geographies: ['county:17031', 'state:48']` keeps Cook + every TX job.
- `_feature_from_marker` test (pytest) — fixture county_fips ends up in the GeoJSON properties.
- FilterPanel rendering test — a `county:17031` chip shows the county-name label.
- ScopedAreaActions on CountyDetail — clicking "Add to search" mutates `mapState.filters.geographies` to include `county:17031` once and only once.

---

## Invariants to preserve (from CLAUDE.md)

1. `mapState.filters` is the **only** write path for filter state. ScopedAreaActions, QuickAdd, FilterPanel chip rendering, and any code touching the geography list must go through it. No parallel copies.
2. `filterJobs(allJobs, mapState.filters, details)` is the canonical filter pipeline — heat, markers, list counts, and scoped previews all read from it. County chips must flow through this single function.
3. `InfoTooltip.svelte` is the canonical tooltip component — reuse it in NationalRoundup, do not invent a new tooltip pattern.
4. Multiple geography chips are ORed with each other and ANDed with non-geographic filters (CLAUDE.md invariant 17). The county chip parser must respect this.
5. No element overlap. NationalRoundup occupies the existing `feature-panel` cell; do not introduce a new layout cell or absolute-positioned container.
6. `ScopedAreaActions` previewable counts must offer "with global filters" and "without global filters" views (CLAUDE.md invariant 16). The county scope inherits this contract from the existing State/Locality usage — do not regress.
7. `_feature_from_marker` is intentionally minimal because `jobs.geojson` is on a 25 MiB Pages limit. Adding `county_fips` (5 chars per feature) is fine; do not pile on additional fields beyond what D.5.26 actually needs.

---

## What NOT to do this session

- Do not start D.5.9 (Federal Real Property layer), D.5.17 (compensation comparator), or D.5.24 (Posting Intelligence) — separate slices, separate PRs.
- Do not bulk-import HistoricJoa for the national card. NationalRoundup must render entirely from existing static exports (`agencies.json`, `states.geojson`, `pay_tables.json`, `cost_of_living.json`, `manifest.json`).
- Do not introduce a new layout cell. NationalRoundup reuses `feature-panel`.
- Do not change `_marker_dataset` query shape — the field is already there. Just expose it in `_feature_from_marker`.
- Do not skip the ScopedAreaActions wiring on CountyDetail. The whole point of this slice is that the four geography surfaces (national / state / locality / county) become symmetric.

---

## Definition of done

- New `NationalRoundup.svelte` rendered as the default FeaturePanel content; "Back to national" pill opens it.
- `ScopedAreaActions` mounted in `CountyDetail.svelte` with the county scope; the with/without-global-filter preview counts work.
- `jobs.geojson` features carry `county_fips` (verify with one new exporter test).
- `filterJobs` honors `county:<fips>` chips; URL state round-trips them.
- FilterPanel labels `county:` chips with the county name.
- `QuickAdd` wired so a click on a county FIPS adds the chip.
- Tests pass: `pytest tests/test_public_map_export*.py tests/test_ingest_scripts.py` clean (the two pre-existing `geo_quality` failures in `tests/test_public_map_export.py` are unrelated and out of scope).
- ROADMAP.md updated: D.5.25 and D.5.26 marked `[x]` with the "Shipped …" note pattern used by prior slices.
- CLAUDE.md gets a paragraph under the public-map shipped notes summarizing what landed.
