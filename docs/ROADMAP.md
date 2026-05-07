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

### Phase B — SvelteKit map skeleton with layered architecture *(NEXT)*

- [ ] Scaffold SvelteKit (`adapter-static`) under `public_map/`.
- [ ] Mapbox GL map with `maxzoom: 9` and per-layer `minzoom`/`maxzoom`.
- [ ] Layer order: basemap → states fill → counties outline → metros outline → localities outline+fill → marker clusters → individual markers.
- [ ] Choropleth metric switcher (open postings, workforce, accessions, separations, remote share, pay-vs-COL).

**Exit:** `npm run dev` renders the layered map; switcher recolors; markers appear past zoom 7; nothing renders past zoom 9.

### Phase C — Popups and click handling

- [ ] `StateRoundup`, `LocalityDetail`, `CountyDetail`, `JobCard` Svelte components.
- [ ] Click resolution: polygon clicks at low zoom; marker clicks at high zoom.
- [ ] `JobCard` lazy-loads its detail entry and renders the full locality-adjusted pay table.

**Exit:** every popup matches reference data exactly for at least three sample features; pay tables match OPM-published values to the cent.

### Phase D — Filters, URL state, styling pass

- [ ] `FilterPanel.svelte` (keyword, agency, series, grade range, salary minimum, remote, hiring path, pay plan).
- [ ] URL-encoded filter state, debounced replaceState.
- [ ] Aesthetic pass: typography, spacing, mobile drawer, layer-transition animations, accessibility audit.

**Exit:** sharing a filtered URL restores the same view; mobile drawer works; Lighthouse ≥ 90.

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
