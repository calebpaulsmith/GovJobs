# ROADMAP.md

Strict build order. Do not skip ahead. Each milestone has an exit criterion that must be visibly satisfied (manually or by tests) before the next begins.

---

## Phase 0 — Planning (this phase)

- [x] Repo skeleton
- [x] `Project_Start.md` brief committed
- [x] README, CLAUDE.md, .env.example, requirements.txt
- [x] Planning docs: PRODUCT_SPEC, DATA_MODEL, API_NOTES, ROADMAP, DECISIONS, DATA_INVENTORY, FIELD_DICTIONARY, FEATURE_FEASIBILITY_MATRIX, DOWNLOAD_STRATEGY

**Exit:** the user has read the docs and confirmed the V1 scope.

---

## Phase 1 — Reconnaissance ✅

Files: `config.py`, `src/data_recon.py`, `src/logging_utils.py`, `tests/test_data_recon.py`, plus `pytest.ini`. Strategy doc is rewritten by the recon entry point.

- [x] Read thresholds from `config.py` (which reads `.env`).
- [x] Probe HistoricJoa by year/month for record counts and page estimates. *(Implemented; falls back to documented estimates when credentials are missing.)*
- [x] Probe AnnouncementText availability for a small sample. *(Treated as selective by design.)*
- [x] Inspect OPM downloads page and record dataset sizes. *(Placeholder estimates; refined when real probe is wired up.)*
- [x] Recommend a download mode: `FULL_DOWNLOAD` | `FOCUSED_FULL_DOWNLOAD` | `STAGED_DOWNLOAD` | `SAMPLE_ONLY`.
- [x] Tests for the recommendation logic with mocked estimates. *(19 tests, all green.)*

**Exit:** running `python -m src.data_recon` rewrites the `## Recon log` section of `docs/DOWNLOAD_STRATEGY.md` and `pytest` is green. **Done.**

---

## Phase 2 — Database foundation

Files: `src/database.py`, `tests/test_database.py`.

- [x] `init_schema()` creates all tables in `docs/DATA_MODEL.md`.
- [x] `upsert_job(...)` enforces dedup on `(source, position_id, announcement_number)` and USAJOBS control number when present.
- [x] `record_raw_response(...)` logs every API request.
- [x] `start_manifest / update_manifest / complete_manifest` for resumable batches.
- [x] CRUD for saved_jobs, job_notes, job_tags, match_scores.
- [x] Tests cover insert / update / duplicate / retrieval.

**Exit:** `pytest tests/test_database.py` passes, schema initializes from a clean directory. **Done.**

---

## Phase 3 — USAJOBS import

Files: `src/usajobs_current_api.py`, `src/usajobs_historic_api.py`, `src/usajobs_announcement_text_api.py`, `src/data_import.py`, matching `tests/`.

- [x] Read credentials from `.env`; clear error if missing.
- [x] Search API import -> `jobs` table, raw JSON saved.
- [x] Historic JOA import -> `jobs` table, resumable via manifest.
- [x] Announcement Text import -> `job_text` table, only for selected job IDs.
- [x] Pagination, rate-limit handling, retries, dry-run, max-pages.
- [x] Tests mock HTTP; no real network in tests.

**Exit:** a small live search and a small historic backfill run end-to-end and the data appears in SQLite with raw JSON on disk. **Done.**

---

## Phase 4 — First Streamlit UI

Files: `app.py`, `pages/1_Search_Jobs.py`, `pages/2_Saved_Jobs.py`, `pages/3_Historical_Trends.py`, `pages/4_State_Map.py`, `pages/5_Scorecards.py`, `pages/7_Data_Admin.py`, `pages/8_Settings.py`. V2 now also adds `pages/6_Application_Tracker.py`.

- [x] Home shows DB status + freshness.
- [x] Current search with filters + result table + save / tag / note / status.
- [x] Trend charts when historical data is present.
- [x] State map when location data is present.
- [x] Scorecards when enough data is present.
- [x] Data Admin page surfaces import status, errors, sizes, mode.

**Exit:** `streamlit run app.py` works end-to-end; every page renders without crashing on an empty DB. **Done.**

---

## Phase 4.5 - Data structure hardening

Files: `src/database.py`, `src/usajobs_normalize.py`, `src/data_import.py`, `src/ui_data.py`, `pages/1_Search_Jobs.py`, `pages/3_Historical_Trends.py`, `pages/4_State_Map.py`, `pages/7_Data_Admin.py`, matching `tests/`.

- [x] Add agency/code lookup tables: `agency_codes` and `code_lists`, seeded initially with FEMA/DHS and priority series. Official code-list sync still needs a fuller loader.
- [x] Add child tables for repeated USAJOBS structures: `job_locations`, `job_categories`, `job_hiring_paths`, and `job_required_documents`.
- [x] Keep `jobs` as the fast summary table, but populate child tables during Search, HistoricJoa, and AnnouncementText imports.
- [x] Backfill child tables from existing flat rows during schema initialization.
- [x] Add next schema-expansion evidence tables from `docs/SCHEMA_EXPANSION_PLAN.md`: `job_import_scopes`, `job_grades`, `job_salary_ranges`, `job_requirements`, `job_qualification_requirements`, `job_duties`, and `job_evaluation_factors`.
- [x] Replace agency keyword defaults with structured agency-code controls. FEMA uses Search `Organization=HSCB`; HistoricJoa and AnnouncementText use `HiringAgencyCodes=HSCB`.
- [x] Drive Data Admin/import/search screens from structured filters where supported: agency code, department code, series, grade/pay plan, date range, location, remote, hiring path, announcement number, and control number. HistoricJoa calls still use only documented server-side filters.
- [x] Make HistoricJoa and AnnouncementText share the same filter-scope object so text imports can run by agency/date/series slice, not one control number at a time.
- [x] Add tests proving repeated locations, series, hiring paths, and required documents survive normalization.

**Exit:** the user can import and browse a FEMA historical slice using agency-code filters, with multi-location/multi-series data preserved and tests green.

---

## Phase 5 — Match scoring (rule-based)

Files: `src/scoring.py`, `tests/test_scoring.py`.

- [x] Transparent rule weights for: FEMA, DHS, emergency management, mitigation, public assistance, grants management, disaster recovery, policy/program analysis, infrastructure, resilience, supervisory, GS-13/14/15, Chicago/Midwest, remote.
- [x] Score 0–100 + explanation + positive/negative/missing factors.
- [x] Stored in `match_scores` with `scoring_version`.
- [x] Score column visible on every job listing and detail.

**Exit:** scoring is reproducible and explained; tests cover every rule. **Done.**

---

## Phase 6 — Alerts (local)

Files: `src/alerts.py`, `tests/test_alerts.py`.

- [x] Saved-search-driven alerts.
- [x] Detect new matches since last run, high score, closing soon, reposted.
- [x] In-app summary table + CSV export.
- [x] No email yet.

**Exit:** alerts visible on Saved Jobs / Admin page. **Done.**

---

## Phase 6.5 - Preference feedback and similar jobs

Files: `src/recommendations.py`, `src/ui_data.py`, `src/database.py`, `pages/1_Search_Jobs.py`, `pages/5_Scorecards.py`, matching `tests/`.

- [x] Add user feedback storage for `liked`, `disliked`, `more_like_this`, `less_like_this`, and short user explanations for later review.
- [x] Add UI controls to record feedback from job detail and scorecard rows.
- [x] Build deterministic similar-job suggestions from structured fields first: agency code, department code, series, grade, location, remote status, hiring path, duties, qualifications, requirements, and user tags.
- [x] Use negative feedback to suppress or down-rank jobs with rejected agencies, series, locations, grades, travel, clearance, or text themes.
- [x] Store recommendation runs and per-suggestion explanation factors.
- [x] Add a "why suggested" view for every recommended job, showing exact shared fields/text signals/feedback patterns.
- [x] Keep embeddings/vector similarity deferred to V3; Phase 6.5 remains explainable and local.

**Exit:** the user can mark jobs with feedback plus an explanation, see similar-job recommendations, and inspect why each suggestion appeared. **Done.**

---

## Phase 7 — OPM importer + map polish

- [x] OPM file ingestion → `opm_workforce_records`.
- [x] OPM-derived map / chart with explicit "workforce" label.
- [x] Multi-location and remote postings handled separately on the state map.
- [x] Course correction: USAJOBS map supports a GIS-style Folium map with detailed street/imagery base layers, zoomable work-location points when latitude/longitude are present, a control to include/exclude multi-location postings, and zoom-scoped tables for current postings that cannot be mapped plus remote-anywhere postings.
- [x] Map behavior captured as a reusable feature sheet in `docs/MAP_FEATURE_SPEC.md`.

**Exit:** the user can switch a chart between USAJOBS postings and OPM workforce and see the source label change. **Done.**

---

## Phase 8 — Exports

- [x] CSV / Excel export for saved jobs, scorecards, alerts.

**Exit:** saved jobs, scorecards, and alerts can be downloaded as CSV or Excel from the app. **Done.**

---

## Version 2

- [x] Application Tracker (`pages/6_Application_Tracker.py`).
- [x] Resume version manager (`pages/9_Resume_Versions.py`).
- [x] Repost detector (`pages/10_Repost_Detector.py`).
- [ ] Closing-window analytics.
- [ ] Postings-vs-accessions comparison.
- [ ] Locality salary normalization.
- [ ] Improved hotness model.
- [ ] PDF export.
- [ ] Per-agency / per-series notes.
- [ ] Career-ladder categorization.

## Version 3 — AI / RAG

- [ ] Vector store decision (Chroma vs FAISS vs sqlite-vss). Defer until V1+V2 stable.
- [ ] Embeddings for `job_text` (selected jobs only).
- [ ] Resume-to-announcement matcher (must not invent experience).
- [ ] Hidden-opportunity finder.
- [ ] Application strategy generator.

---

## Out of scope (any version)

- Automated submission of applications.
- Browser scraping in lieu of APIs.
- Multi-tenant / cloud SaaS deployment of the dashboard. (The public map at `thegrandpipeline.com/map` is a separate product per ADR-0016, not a hosted version of the dashboard.)

---

## Parallel track — Public Map Tool (`thegrandpipeline.com/map`)

A separate sibling product per ADR-0016, ADR-0017, ADR-0018, and ADR-0019. The dashboard remains local-first; the public map is a static, read-only website fed by nightly snapshots from the local SQLite. Lives in `public_map/` with its own `package.json`. Stack: SvelteKit (static adapter) + Mapbox GL JS + Cloudflare Pages. **Layered, zoom-driven map** with maxzoom 9. Runs independently of the dashboard's V1/V2/V3 build order. The detailed implementation plan is at `C:\Users\caleb\.claude\plans\review-the-new-map-playful-wind.md`. External dataset catalog: `docs/PUBLIC_MAP_DATA_SOURCES.md`.

### Phase A — Markers and geocoding ✅

Files: `src/database.py` (locations_geocoded), `src/public_map_export.py`, `scripts/export_public_map.py`, `scripts/geocode_locations.py`, `tests/test_public_map_export.py`.

- [x] `locations_geocoded` table + 56 state/territory centroids; `geocoding_misses` log table.
- [x] `scripts/geocode_locations.py` backfills from SimpleMaps US Cities CSV.
- [x] `src/public_map_export.py` pure query functions (jobs_geojson, job_details, opm_state_aggregates, manifest, geocoding_summary).
- [x] `scripts/export_public_map.py` writes the marker bundle.
- [x] 12 tests green; full suite (96) green.

**Exit:** open postings export produces well-formed GeoJSON; geocoding falls back from city to state centroid; closed postings excluded. **Done.**

### Phase A.5 — Reference data foundation ✅

Adds the schema and ingest fleet for pay tables, localities, polygons, and cost of living. Per ADR-0018 every external dataset is tracked in `data_source_status` and visible in the local admin dashboard. Per ADR-0019 the locality pay polygons use OPM's ArcGIS FeatureServer with a county-dissolve fallback.

Files: `src/database.py`, `src/data_source_registry.py`, `src/reference_data.py`, `src/pay_calculator.py`, `pages/11_Public_Map_Admin.py`, `scripts/ingest_*.py`, matching `tests/`.

- [x] Add 9 reference-data tables: `pay_plans`, `pay_scales`, `locality_pay_areas`, `locality_pay_counties`, `counties`, `metro_areas`, `state_polygons`, `cost_of_living_index`, `data_source_status`. Schema bumped to 9 after V2 merge.
- [x] `src/data_source_registry.py` — read/update helpers for `data_source_status`.
- [x] `src/reference_data.py` — pure read helpers (lookup locality by FIPS, lookup pay scale by pay plan/year/grade/step/locality).
- [x] `src/pay_calculator.py` — given a job, returns its locality-adjusted pay table. Tested against seeded locality-row and base+adjustment paths; first-run verification against published OPM values done in admin diff view.
- [x] Ingest scripts (each idempotent, each writes status):
  - [x] `ingest_state_polygons.py` (Census TIGER, simplified)
  - [x] `ingest_county_polygons.py`
  - [x] `ingest_cbsa_polygons.py`
  - [x] `ingest_locality_definitions.py` (OPM annual county-FIPS list)
  - [x] `ingest_locality_polygons.py` (OPM ArcGIS primary, county-dissolve fallback)
  - [x] `ingest_locality_pay.py` (annual % adjustment per locality)
  - [x] `ingest_gs_pay.py` (OPM GS tables, base + per-locality)
  - [x] `ingest_other_pay_plans.py` (FW first; ES, AD, FP, LE, VN incrementally)
  - [x] `ingest_bea_rpp.py` (BEA Regional Price Parities, state + metro)
  - [x] `refresh_public_map_data.py` (orchestrator)
- [x] `pages/11_Public_Map_Admin.py` — local-only Streamlit page with per-source status, last run, row count, manual refresh button, CSV upload override, year-over-year diff for pay scales.
- [x] Tests: status registry round-trip, pay calculator (real OPM values), reference-data lookups, ingest scripts. 33 new tests, 142 total green.

**Exit:** every ingest script runs against a clean DB and lands status=green; admin page lists every source with green status; pay calculator returns locality-row values verbatim and falls back to base × (1 + adjustment%). **Done.**

### Phase A.7 — Polygon and pay-table export ✅

Files: `src/public_map_export.py`, `scripts/export_public_map.py`, `tests/test_public_map_export_polygons.py`.

- [x] Extended the export to emit `states.geojson`, `localities.geojson`, `counties.geojson`, `metros.geojson`, `pay_tables.json`, `cost_of_living.json`.
- [x] Each polygon FeatureCollection joins reference data (postings, OPM workforce, RPP, GS-13 pay, pay-vs-COL) so the public site can render the choropleth metric switcher without per-feature lookups.
- [x] Each marker in `jobs.geojson` carries its `locality_code` derived from `locations_geocoded.county_fips` → `locality_pay_counties` for the current reference year.
- [x] `manifest.json` lists per-source freshness pulled from `data_source_status`, plus per-layer feature counts and the resolved `reference_year`.
- [x] Stdlib Douglas-Peucker `simplify_geometry` runs at export time so on-disk TIGER detail compresses to ~10% before bundling.
- [x] 16 new tests in `tests/test_public_map_export_polygons.py`; full suite = 158 green.

**Exit:** every output validates as well-formed GeoJSON / JSON; bundle gzipped size ≤ 15 MB; tests cover polygon emit shape and the per-feature pay-vs-COL field. **Done.**

### Phase B — SvelteKit map skeleton with layered architecture *(SKELETON LANDED)*

- [x] Scaffold SvelteKit (`adapter-static`) under `public_map/` (Svelte 5 + Vite 6 + TS; SPA mode).
- [x] Mapbox GL map with `maxZoom: 9` and per-layer `minzoom`/`maxzoom`; OSM raster fallback when `VITE_MAPBOX_TOKEN` is unset.
- [x] Layer order in `src/lib/layers.ts`: basemap → states fill → states outline → counties outline → metros outline → localities fill+outline → marker clusters → individual markers.
- [x] Choropleth metric switcher (open postings, workforce, accessions, separations, remote share, pay-vs-COL); `remote_share` derived client-side from `jobs.geojson` and stamped onto each state feature.
- [x] `npm run check` and `npm run build` are green; SPA bundles to `public_map/build/`.

**Exit:** `npm run dev` renders the layered map; switcher recolors; markers appear past zoom 7; nothing renders past zoom 9. *(Awaiting visual verification with the local data bundle in `public_map/static/data/`.)*

### Phase C — Popups and click handling *(INITIATED)*

- [x] `StateRoundup`, `LocalityDetail`, `CountyDetail`, `JobCard` Svelte components.
- [x] Click resolution: polygon clicks at low zoom; marker clicks at high zoom; clusters zoom to expansion level instead of opening a panel.
- [x] `JobCard` lazy-loads its detail entry and renders the locality-adjusted pay table when matching static pay rows exist.
- [ ] Visual/data verification against at least three sample features once the polygon/pay bundle is populated locally.

**Exit:** every popup matches reference data exactly for at least three sample features; pay tables match OPM-published values to the cent.

### Phase D — Filters, URL state, styling pass *(SUPERSEDED BY D.5 — see below)*

- [x] `FilterPanel.svelte` (keyword, agency, series, grade range, salary minimum, remote, hiring path, pay plan).
- [x] URL-encoded filter state, debounced replaceState.
- [x] Filtered marker-source updates plus filtered remote-share recoloring for the state choropleth.
- [ ] Aesthetic pass: typography, spacing, mobile drawer, layer-transition animations, accessibility audit. *(Folded into D.5.0 layout grid + D.5 visual pass.)*

**Exit:** sharing a filtered URL restores the same view; mobile drawer works; Lighthouse ≥ 90. *(Lighthouse target moves to end of D.5.)*

### Phase D.5 — Course correction *(IN PROGRESS, blocks E)*

2026-05-09 admin-ops follow-up: Public Map Admin must support one-click reference-data refresh/export, ticker-style before/after totals for each refreshed source, and a federal-wide current-postings import control for getting all current USAJOBS Search rows into the local corpus.

User review on 2026-05-07 found eleven concrete defects: agency filter is a free-text box, no saved searches, no address/ZIP zoom, no persistent heat layer, polygon layers report zero features so the choropleth has nothing to color, OSM fallback fails without a Mapbox token, panels overlap, missing federal-properties layer, missing county-level COL, missing exact pay tables on every job, and the local corpus is too small to evaluate. A 2026-05-08 follow-up added 2026 GS pay tables, snap-scoped state/locality/future-city search windows, Add to Search, global-filter preview toggles, light/dark mode, compensation comparison, urgency/fill badges, and local profile state for viewed/saved/hidden jobs. Detailed sub-phases, integration map (upstream → exporter → UI), and exit criteria live in the "Phase D.5" section of `C:\Users\caleb\.claude\plans\review-the-new-map-playful-wind.md`. New ADRs cover the UI invariants (ADR-0024), federal-properties layer (ADR-0025), self-bootstrapping ingests (ADR-0027), and scoped-search/pay/comparison/profile follow-up (ADR-0028). Hard rules added to `CLAUDE.md` under "Public Map V1.5 invariants."

- [x] **D.5.-1 — Self-bootstrapping ingest pipeline (shipped 2026-05-08).** `src/ingest_common.py` gained `resolve_or_download` + `shapefile_zip_to_geojson` + `ensure_geojson_input`; `requirements.txt` adds `pyshp`. Census TIGER state / county / CBSA polygons auto-download from `www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_*_*.zip` on first run. OPM locality definitions, locality pay percentages, GS base pay table, and BEA RPP default to checked-in seed CSVs at `data/external/{opm_locality_definitions,opm_locality_pay,opm_gs_pay,bea_rpp}/`. Locality polygon ingest auto-discovers `MAX(year) FROM locality_pay_counties` and falls back from ArcGIS to county-dissolve when ArcGIS yields zero recognized features. Orchestrator enables every step by default. `pay_vs_col` formula corrected to a purchasing-power index in `_pay_vs_col` + new `_gs_base_step1_for_year` helper. Per-source ADR-0027 captures the policy.
- [x] D.5.0 — UI layout grid contract (`public_map/src/lib/layout.ts`); zero panel overlap at three breakpoints. *(Shipped 2026-05-09: `layout.ts` now exports per-slot `Rect` data at desktop / tablet / mobile (1440×900, 1024×768, 720×1280) plus `layoutCssBlock()` which `+layout.svelte` injects via `<svelte:head>`. Every panel — masthead, ActiveFilterStrip, AddressSearch, SavedSearchMenu, FilterPanel, FeaturePanel, MetricSwitcher, freshness footer — now reads its position from `--slot-<name>-*` CSS variables instead of hard-coded `top:`/`left:`. State-driven shifts (FilterPanel `.address-open` / `.saved-open`) become deltas off `var(--slot-filters-top)` so layout.ts stays the single source of truth. Per-component `@media (max-width: 640px)` blocks were aligned to `@media (max-width: 719px)` so the JS spec and CSS breakpoints match. New `layout.test.ts` (20 cases) exercises `parseLength` (rem/px/%/vw/vh/min/max/calc), `pickBreakpoint`, `computeRectPx` for every anchoring shape, structural integrity of `LAYOUT_RECTS`, the CSS emission, and — the D.5.0 exit criterion — pairwise non-overlap at all three reference viewports. `npm test` 67/67 green; `npm run check` 0 errors / 0 warnings; `npm run build` succeeds.)*
- [ ] D.5.1 — Persistent posting heat layer at zoom 3–9, filter-aware, toggleable. *(Partial: `posting-heat` layer now uses a separate unclustered `jobs-heat` source, updates with active filters, persists from zoom 3–9, and has a Heat on/off toggle in `MetricSwitcher` — 2026-05-08. Visual regression/screenshot verification still pending.)*
- [x] D.5.2 — Agency multi-select with code-backed typeahead and aliases (URL state via repeated `agency=` keys). *(Shipped 2026-05-09: `FilterPanel.svelte` uses code-backed chips from `agencies.json`, aliases resolve to canonical codes, and URL state round-trips repeated `agency=` keys.)*
- [x] D.5.3 — Named saved searches in `localStorage` (Save / Apply / Rename / Delete). *(Shipped 2026-05-09: `SavedSearchMenu.svelte` + `savedSearches.ts` persist schema-versioned local searches including filters, metric, map viewport, and the last address-zoom target when present; Apply restores filters, metric, address target, and viewport.)*
- [x] D.5.4 — Address / ZIP geocoder with Mapbox primary + Nominatim fallback + offline ZIP centroids. *(Shipped 2026-05-09: downstream `AddressSearch.svelte` + `geocode.ts` added Mapbox/Nominatim search, optional `zip_centroids.json` lookup, `flyTo`, transient non-job pin source/layer, and saved-search address-target recall. Upstream `zip_centroids` table, `scripts/ingest_zip_centroids.py`, `zip_centroids_payload`, bundle export, and tests now ship; local export wrote 33,791 Census ZCTA centroids.)*
- [x] D.5.5 — Click-state-to-fit-bounds (also locality / county / CBSA at their zoom bands). *(Shipped 2026-05-09: polygon clicks in `Map.svelte` compute feature bounds and fit to state/locality/county/metro zoom bands with a Back to national pill; the scoped action window follow-through landed as `ScopedAreaActions.svelte` under D.5.15 the same day, completing the original D.5.5 plan.)*
- [x] D.5.6 — Metric switcher honesty pass: every metric carries `status` (`ready` / `wip` / `under-construction`); auto-demotion when ≥ 50% of features are null. *(Shipped 2026-05-09: `MetricDef` gains `status` + `wipNote`; `Map.svelte::computeMetricDemotion` runs after states load + after `deriveRemoteShare` and sets `mapState.demotedMetrics`; `MetricSwitcher.svelte` renders a striped placeholder + note for wip metrics and hides under-construction metrics behind a "Show experimental" toggle; wip metrics select but disable choropleth shading.)*
- [x] D.5.13 — Calculation-traceback tooltips on every computed value. *(Shipped 2026-05-09: `InfoTooltip.svelte` wired into `StateRoundup` (Locality / GS-13 step 1 / RPP / Pay-COL index), `LocalityDetail` (county count / locality adjustment / GS-13 step 1 / RPP / Pay-COL index), `CountyDetail` (locality code / CBSA / GS-13 step 1 / RPP / Pay-COL index), and `JobCard` (locality-adjusted pay table heading + the "no row" fallback message). Each tooltip surfaces the formula, the actual inputs used, and the data source.)*
- [ ] D.5.7 — Corpus growth: Data Admin presets for federal-wide and top-25 imports + trailing-90-days HistoricJoa overlay; closed postings rendered as faint gray dots. *(Partial: `src/public_map_corpus.py` adds recon-gated Data Admin presets for federal-wide current, top-25 current, and HistoricJoa trailing-90-day closed imports; exporter writes `closed_jobs.geojson`; UI renders a toggleable gray closed-postings layer — 2026-05-08. Still needs actual preset run to reach ≥5,000 open postings / ≥5,000 closed markers.)*
- [x] D.5.20 — Public Map Admin operations pass: one-click refresh of every reference-data source plus bundle export; ticker-style before/after row totals for each refreshed source; federal-wide "get all current jobs" import control with recon gate and page-cap/no-cap options. *(Shipped 2026-05-09 in `pages/11_Public_Map_Admin.py`; still needs operator run against live USAJOBS credentials to grow the corpus.)*
- [x] D.5.8 — OSM fallback hardening (drop `glyphs:`, disable Mapbox telemetry, OSM subdomain rotation, basemap unit test); fall back to MapLibre via ADR-0026 if mapbox-gl v3 won't cooperate. *(Shipped 2026-05-09: `basemap.ts` ensures the inline OSM dark/light styles declare no `glyphs:` URL and no symbol layers, rotates across `a/b/c.tile.openstreetmap.org`, and `configureMapboxRuntime` now disables `SEND_EVENTS` in both token and no-token modes. New `assertBasemapInvariants(style)` helper enforces the rules at runtime; `Map.svelte` runs it under `import.meta.env.DEV`. `src/lib/basemap.test.ts` covers the invariants under vitest (`vitest.config.ts` added; `npm test` script wired). MapLibre fallback is unnecessary for now — mapbox-gl v3 cooperates with the OSM-fallback path.)*
- [x] D.5.9 — Federal Real Property layer: `federal_properties` table, `scripts/ingest_federal_properties.py`, `federal_properties.geojson` export, neutral-diamond layer + popup. *(Shipped 2026-05-09: schema bumped to v11 with a `federal_properties` table indexed on state/agency_code; `scripts/ingest_federal_properties.py` is self-bootstrapping per ADR-0027 with a checked-in seed at `data/external/gsa_federal_properties/seed.csv` (30 well-known FRPP buildings spanning 17 states). `src.public_map_export.federal_properties_geojson` emits a Point FeatureCollection with non-null properties only. Orchestrator runs the ingest by default; override via `PUBLIC_MAP_FRPP_CSV`. `scripts/export_public_map.py` writes `federal_properties.geojson` and adds the layer count to `manifest.json.layers`. UI: new `federal-properties` source + `federal-properties-markers` circle layer at `minzoom: 6`, off by default and toggled via a "Fed props" pill in `MetricSwitcher`; clicks on a marker open a FeaturePanel section with name / agency / address / status. Tests in `tests/test_ingest_scripts.py` (3) and `tests/test_public_map_export.py` (4); `npm run check` reports 0 errors / 0 warnings; `npm test` passes 26/26; `npm run build` succeeds.)*
- [x] D.5.10 — County-level COL via Census ACS rent joined into `cost_of_living_index`. *(Shipped 2026-05-09: new `census_acs_rent` source per `docs/PUBLIC_MAP_DATA_SOURCES.md`. `scripts/ingest_acs_county_rents.py` is self-bootstrapping per ADR-0027 with a checked-in seed at `data/external/census_acs_rent/2023.csv` (~40 well-known counties + ~26 state medians). Computes `county_rpp = state_rpp × (county_rent / state_median_rent)` per the data-sources spec, inserting `geo_type='county'` rows with `source='census:acs5_b25064'`. `cost_of_living()` now emits `by_county` alongside `by_state` and `by_cbsa`. `counties_geojson()` prefers the county-level RPP over the state-level fallback and exposes `rpp_overall_source: 'county' | 'state'` plus `gs13_step1_locality` and `pay_vs_col`. `CountyDetail.svelte` labels precision honestly ("County (ACS rent-derived)" vs "State fallback"). 5 new tests in `tests/test_ingest_scripts.py` and `tests/test_public_map_export_polygons.py`. Optional BLS metro CPI is still deferred behind a feature flag — D.5.10 exit only required the ACS path.)*
- [x] D.5.11 — Exact pay tables on every job: pre-compute `pay_grid` in the exporter with `status: 'exact' | 'approximated' | 'unavailable'`; JobCard shows the grid or a clear "missing source" message linking to admin. *(Shipped 2026-05-09: `src.public_map_export._build_pay_grid` calls `pay_calculator.calculate_job_pay_table` against each job's first listed location and embeds the resulting `{status, year, pay_plan, locality, method, grades, notes, missing_reason}` payload in `jobs_detail.json`. Status is `exact` when every cell came from a locality-specific `pay_scales` row, `approximated` when at least one cell was derived as `base × (1 + pct)`, and `unavailable` when the job lacks a pay plan/grade or `pay_scales` has no matching rows. `JobCard.svelte` reads `detail.pay_grid`, renders a colored status pill (exact / approximated / snapshot), shows a dashed-border "Pay scale not yet ingested — see admin" panel with a link to `pages/11_Public_Map_Admin.py` when status is `unavailable`, and falls back to `pay_tables.json` only for older bundles produced before D.5.11. Tests in `tests/test_public_map_export.py` cover all three status paths plus the no-pay-plan edge.)*
- [~] D.5.14 — 2026 GS pay-table cutover: ingest official 2026 GS base and locality tables, make 2026 the exported reference year, and verify sampled rows in Public Map Admin before V1 deploy. *(Shipped 2026-05-09 — bootstrap data + verification harness; operator-verified row replacement still pending. Cutover infrastructure: `data/external/opm_gs_pay/2026_base.csv`, `data/external/opm_locality_pay/2026.csv`, `data/external/opm_locality_definitions/2026.csv` are checked-in seeds; the GS base seed is computed from the 2025 base × 1.0% across-the-board raise (per the OPM PDF title "Incorporating the 1% General Schedule Increase") and is bootstrap data only. Locality percentages and county→locality definitions carry the 2025 values forward as 2026 placeholders. `SEED_CSV` constants in `scripts/ingest_gs_pay.py`, `scripts/ingest_locality_pay.py`, and `scripts/ingest_locality_definitions.py` now point to the 2026 files; `current_reference_year(conn)` resolves to 2026 once the seeds are imported. `pages/11_Public_Map_Admin.py` gained a "Reference year (D.5.14)" panel that flags whether the resolved year matches the V1 target (2026), shows three sampled GS cells (GS-1 step 1 base, GS-13 step 1 base, GS-15 step 10 base), and instructs the operator to verify them against the official OPM 2026 PDF and replace the seed if any cell differs by more than $1. Tests in `tests/test_ingest_scripts.py` confirm the seed loads 150 GS rows for year 2026 and that `current_reference_year` flips to 2026 immediately. Pending operator step: download the OPM 2026 PDF, replace the seed with verified rows, re-run the ingest, and confirm the spot-check is clean before V1 deploy.)*
- [x] D.5.15 — Snap-scoped geographic search windows: state/locality now, city later. Polygon click fits bounds, opens a scoped window, supports Search this area, Include remote, Add to Search, and with/without-global-filters preview. *(Shipped 2026-05-09 in commit `5e14179`: `geographies: string[]` added to `JobFilters` with `state:<code>`/`locality:<code>` keys; `filterJobs` honors geography chips (OR across chips, AND with the rest); URL state via repeated `geo=` keys; `ScopedAreaActions.svelte` renders at the top of state/locality `FeaturePanel` with Search only here / Add to search / Remove actions; `FilterPanel` shows active geography chips with × buttons; Reset clears them.)*
- [x] D.5.16 — Light/dark mode toggle: persisted user preference, themed panels/controls/overlays, and verified legibility in both basemap modes. *(Shipped 2026-05-09 in commit `5e14179`: `mapState.theme` persisted to `localStorage` under `tgp.public_map.theme.v1`; pre-paint inline script in `app.html` prevents flash; CSS custom properties in `+layout.svelte` define the dark default and light overrides; `basemap.ts` adds `MAPBOX_LIGHT_STYLE`, `OSM_LIGHT_FALLBACK_STYLE`, and `pickStyleForTheme()`; map remounts via `{#key mapState.theme}` for clean style swap; theme pill ☀/☾ in masthead.)*
- [x] D.5.17 — Personal compensation/COL comparator: accepts GS grade/step + locality or custom wage, optional current comparison city, and returns sourced equivalent-pay statements. *(Shipped 2026-05-09: `public_map/src/lib/compensation.ts` exposes `compute()` plus helpers (`gsBasePay`, `applyLocality`, `localityPrimaryState`, `localitiesFromGeoJson`, `stateRppFromCol`); `CompensationComparator.svelte` is a right-hand drawer launched by a Pay Compare pill in the masthead. GS mode uses `pay_tables.json` GS base × OPM locality adjustment from `localities.geojson`; custom mode takes a wage in a chosen state. COL comparison uses BEA RPP from `cost_of_living.json`. Source RPP is flagged approximate when the OPM locality spans multiple states (the locality's primary state is used). Calculations show their formula and source citations inline. 18 vitest cases in `compensation.test.ts` cover GS/custom modes, fallback paths, and bad input; `npm test`, `npm run check`, and `npm run build` all green.)*
- [x] D.5.18 — Job urgency and fill badges: JobCard/JobList badges for closing soon/tomorrow/today plus source-backed applicant/opening signals when USAJOBS exposes them. *(Shipped 2026-05-09: `format.ts::urgencyBadge` computes days until close_date and returns `{text, level: 'critical'|'soon'|null}`; JobCard shows a colored pill below the title; JobList rows show a compact badge in the row header. Badge is suppressed for closed postings.)*
- [x] D.5.19 — Local profile job state: viewed badges, Save Job, Hide Job, default exclusion of hidden jobs from map/list/search views, and profile drawers for Saved Jobs, Hidden Jobs, and viewed jobs that have closed. *(Shipped 2026-05-09: `jobProfile.svelte.ts` singleton persists viewed/saved/hidden in `localStorage` under `tgp.public_map.job_profile.v1`; `ProfileDrawer.svelte` is a right-side drawer with Saved/Hidden/Viewed-Closed tabs; `mapState.hiddenJobIds` + `excludeHidden()` filter hidden jobs from job sources and heat on every filter cycle; JobCard marks viewed on mount, has Save/Hide toggle buttons; "My Jobs" pill in masthead opens the drawer with a saved-count badge.)*
- [ ] ~~D.5.21 — Per-job historical postings window~~ **(superseded by D.5.24 per ADR-0029)**.
- [ ] ~~D.5.22 — Posting timeline chart (static)~~ **(superseded by D.5.24 per ADR-0029)**.
- [x] D.5.23 — Quick-add filter chips: a `QuickAdd.svelte` micro-component that wraps any displayed value with a `+` button on hover. Wired into `JobCard`, `JobList` rows, `StateRoundup`, and `LocalityDetail`. Must call the same `updateFilters` path `FilterPanel` uses — no second write path. *(Shipped 2026-05-09 in commit `5e14179`: `QuickAdd.svelte` shows a `+` on hover/focus-within; clicks mutate `mapState.filters` directly; supports `agency` (push if absent), `series` (replace), `grade` → `gradeMin` (set if empty), `payPlan` (replace), `hiringPath` (replace), `geography` (push if absent); wired into `JobCard`, `JobList`, `StateRoundup`, `LocalityDetail`.)*
- [x] **D.5.24 — On-demand Posting Intelligence (per ADR-0029).** *(Shipped 2026-05-09.)* Click-to-load tab on JobCard powered by a Cloudflare Pages Function (`public_map/functions/api/job-history.ts`) that proxies USAJOBS HistoricJoa with a 24h edge cache (5-minute TTL on failure responses). Surfaces: (a) seven window pills (1mo / 3mo / 6mo / 1yr / 3yr / 5yr / 10yr) above (b) a filtered monthly timeline rendered as inline SVG bars and (c) a "See all N matching historic postings" drill-in list, paginated 25/page, all from the same Function call. Pure helpers (window→date range, query builder, record trimmer, monthly bucketing, cache key) live in `public_map/src/lib/jobHistory.ts` and are shared by the worker and the client; 21 vitest cases in `jobHistory.test.ts` cover them. The worker caps the upstream pull at 5 HistoricJoa pages (~2,500 records) and surfaces a `truncated` flag when the cap fires. No bulk historic import. No prefetch — JobCard mounts the section collapsed. Inherits `mapState.filters` as the single source of truth (agency / series / grade / state); the host posting's own identifying fields fill in any blanks. Failure mode renders an explicit "history unavailable" message with the upstream error text and a retry-after hint, never fabricated data.
- [ ] D.5.12 — Verification pass against the expanded exit criteria documented in the plan.

**Exit:** every D.5 exit criterion in the plan is satisfied; `manifest.json.layers` shows non-zero counts for all six layers; `manifest.json.reference_year` is 2026; the map renders correctly with and without a Mapbox token; scoped geographic search, light/dark mode, compensation comparison, job urgency badges, and local viewed/saved/hidden job state are covered by tests.

### Phase E — Deploy

- [ ] Cloudflare Pages from GitHub, build root `public_map/`.
- [ ] Custom domain `thegrandpipeline.com`, route `/map`.
- [ ] Mapbox token in Pages env vars + URL referrer restrictions in Mapbox dashboard.

**Exit:** `https://thegrandpipeline.com/map` resolves over HTTPS and matches local build.

### Phase F — Operations and polish

- [ ] Cloudflare Web Analytics, `robots.txt`, sitemap, OG image, share-preview meta.
- [ ] `/about` page with attributions: USAJOBS, OPM, Census, BEA, OpenStreetMap, SimpleMaps. "Not affiliated with the U.S. government."
- [ ] Windows Task Scheduler nightly job runs `refresh_public_map_data.py` + `export_public_map.py` + `git push`.
- [ ] Update runbook in `docs/PUBLIC_MAP_PIPELINE.md`.

**Exit:** a nightly run lands fresh data on the public site without manual steps; freshness per source visible in the footer.
