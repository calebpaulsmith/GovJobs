# DECISIONS.md

Architecture decision log. Append-only. Each entry is a decision that should outlive the conversation that produced it.

Format:

```text
## ADR-NNNN â€” Title
Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by ADR-XXXX
Context:
Decision:
Consequences:
```

---

## ADR-0001 â€” Local-first, single-user, SQLite
Date: 2026-05-04
Status: Accepted

**Context.** The user is one person who runs the app locally and is not a software engineer. The data is public. There is no need for hosting, auth, or multi-tenancy.

**Decision.** Version 1 is a Streamlit + SQLite single-user app run on the user's machine. No FastAPI, React, Docker, Postgres, or cloud deployment in V1.

**Consequences.** Setup is `pip install -r requirements.txt` + a `.env` file. No DBA, no auth, no scaling concerns. Future migrations to Postgres are possible because we keep DB access in `src/database.py`.

---

## ADR-0002 â€” Posting data and workforce data are kept separate
Date: 2026-05-04
Status: Accepted

**Context.** USAJOBS publishes *announcements*. OPM publishes *workforce composition, accessions, and separations*. Conflating these is a common analytic mistake.

**Decision.** The schema separates `jobs`/`job_text` (USAJOBS) from `opm_workforce_records` (OPM). Charts must label which source they come from. Joining the two requires a footnoted explanation.

**Consequences.** No "hire rate per posting" metric in V1 â€” the comparison isn't meaningful. Maps show two switchable layers.

---

## ADR-0003 â€” Reconnaissance gates large downloads
Date: 2026-05-04
Status: Accepted

**Context.** USAJOBS HistoricJoa and OPM datasets can be very large. A naÃ¯ve full pull would burn time, disk, and rate-limit budget.

**Decision.** Before any large download, the recon script (`src/data_recon.py`) estimates size, paging, and runtime, then writes a `FULL_DOWNLOAD` / `FOCUSED_FULL_DOWNLOAD` / `STAGED_DOWNLOAD` / `SAMPLE_ONLY` recommendation to `docs/DOWNLOAD_STRATEGY.md`. The user explicitly approves the mode.

**Consequences.** All importers accept a download-mode argument that constrains scope. Resumable manifests track progress so partial pulls aren't wasted.

---

## ADR-0004 â€” Rule-based scoring in V1; LLM only in V3
Date: 2026-05-04
Status: Accepted

**Context.** Match scoring is core to the app. LLM-based scoring is opaque, costs money, and is unnecessary for the tilt the user wants (FEMA / DHS / GS-13â€“15 / Chicago / Midwest / remote).

**Decision.** V1 scoring is deterministic, transparent, rule-based. Each score returns a 0â€“100 number plus positive factors, negative factors, and missing info. LLM-based rÃ©sumÃ© matching arrives in V3 only.

**Consequences.** Scoring is testable and reproducible. We can iterate weights without re-embedding any data. Scoring version is stored with each row so historical scores stay interpretable.

---

## ADR-0005 â€” Raw API responses are first-class artifacts
Date: 2026-05-04
Status: Accepted

**Context.** APIs change. Bugs in the parser can corrupt the DB silently. We need to be able to re-derive the DB from raw bytes.

**Decision.** Every API response is written verbatim to `data/raw/{source}/{endpoint}/{date}/{hash}_{page}.json` and logged in `raw_api_responses`. Re-running the importer against existing raw files reproduces the DB without hitting the network.

**Consequences.** Disk usage grows with every pull. Recon estimates raw size as part of the mode recommendation. `data/raw/` is gitignored.

---

## ADR-0006 â€” Tests use mocked HTTP, never real USAJOBS
Date: 2026-05-04
Status: Accepted

**Context.** Hitting USAJOBS in CI would burn rate limit and break offline.

**Decision.** Use the `responses` library to stub HTTP in `tests/`. No test makes a network call. Importer functions accept a `dry_run=True` flag that returns a synthetic structure for higher-level tests.

**Consequences.** Tests are fast and offline. We need to keep stub fixtures up to date when the API shape changes; recon-step output helps spot drift.

---

## ADR-0007 â€” Streamlit pages are presentation only
Date: 2026-05-04
Status: Accepted

**Context.** Logic that lives in Streamlit pages is hard to test and easily duplicated.

**Decision.** Pages call into `src/` for everything: queries, scoring, importers, exports. Pages contain only UI wiring and presentation. Database access goes through `src/database.py`.

**Consequences.** Pages stay short. Replacing the UI later (FastAPI + React in a hypothetical V4) is mostly a port of the page layer.

---

## ADR-0008 â€” No automated job applications, ever
Date: 2026-05-04
Status: Accepted

**Context.** Auto-applying to federal jobs is a bad idea â€” it harms the user's reputation and violates USAJOBS terms.

**Decision.** The app never submits applications, fills application forms, or signs into usajobs.gov on the user's behalf. Saved jobs link out to the official USAJOBS page.

**Consequences.** "Application" features are always tracking-only.

---

## ADR-0009 â€” Recommendation formula: focused = 20%, staged â‰¤ 10 passes
Date: 2026-05-04
Status: Accepted

**Context.** `recommend_mode` in `src/data_recon.py` needs concrete numbers for "what counts as focused" and "how many passes is too many for staged."

**Decision.**
- A focused subset is modeled as 20% of the full dataset (`focused_factor=0.20`). This roughly matches a slice scoped to target agencies (FEMA, DHS, CISA, HUD, FIMA, USACE, etc.) and the 10 priority series.
- A staged pull is feasible if `passes_needed â‰¤ 10` AND the final DB still fits the configured `MAX_DATABASE_GB`. `passes_needed` is computed against `MAX_FULL_DOWNLOAD_GB`, `MAX_FULL_DOWNLOAD_ROWS`, and `MAX_IMPORT_HOURS`.
- If neither holds, the recommendation is `SAMPLE_ONLY`.

These constants are keyword arguments to `recommend_mode`, so they're tunable per-call without rewriting the function.

**Consequences.** The two thresholds (focused_factor and staged_max_passes) are independent: a dataset that fails focused at 20% but only needs 6 passes still gets STAGED. If we later tighten or loosen "what counts as focused," only the call site changes â€” the recommendation logic stays pure and tested.

---

## ADR-0010 â€” Recon falls back to documented estimates when credentials are missing
Date: 2026-05-04
Status: Accepted

**Context.** `python -m src.data_recon` should be useful before the user pastes their USAJOBS API key into `.env`, but it must never silently mislead them.

**Decision.** Probes detect missing/placeholder credentials and return `DatasetEstimate` rows built from order-of-magnitude defaults (4M HistoricJoa records, ~4 KB/record, 200k records/h throughput, etc.). Each fallback row sets `confidence="low"`, `probed=False`, and a `notes` line stating "no credentials." The strategy doc renders these flags so the user can tell at a glance whether the recommendation is live or estimated.

**Consequences.** First-run UX works without a key. Once credentials are added, the same script writes a fresh `## Recon log` with `confidence=medium` rows and updated estimates. No code change needed.

---

## ADR-0011 - REST docs are canonical for API parameters; SIF docs are canonical for field semantics
Date: 2026-05-05
Status: Accepted

**Context.** The repo includes local SIF guide and data-dictionary files, and USAJOBS also publishes live REST API documentation. The two sources overlap, but they answer different questions.

**Decision.** Importer query parameters must be verified against the official USAJOBS developer docs before coding. The local SIF docs are used to understand field meaning, required/conditional status, repeatability, text-section semantics, and code-list intent.

**Consequences.** We avoid broken REST calls caused by SIF/XML field names, while still using the richer local dictionaries to design the database and UI. `docs/USAJOBS_DATA_STRUCTURES.md` is the reconciliation file for this.

---

## ADR-0012 - Filter-first imports and UI
Date: 2026-05-05
Status: Accepted

**Context.** Keyword searches such as `FEMA` are noisy and can hide the structured shape of USAJOBS data. The APIs expose agency, department, series, date, grade, location, and other filters.

**Decision.** Import scopes and UI search controls should be built from structured filters first. Agency targeting uses codes: Search uses `Organization=HSCB` for FEMA, while HistoricJoa and AnnouncementText use `HiringAgencyCodes=HSCB`.

**Consequences.** Saved searches, historical imports, scorecards, and maps become reproducible. Keyword search remains available as a secondary text filter, not the primary import mechanism.

---

## ADR-0013 - Keep jobs flat for scanning, add child tables for repeated structures
Date: 2026-05-05
Status: Accepted

**Context.** The current `jobs` table is easy to query, but SIF and REST data show repeated locations, occupational series, hiring paths, and required documents. A single row cannot faithfully represent those structures.

**Decision.** Keep `jobs` as the summary/index table, and add child tables for repeated structures in Phase 4.5: `job_locations`, `job_categories`, `job_hiring_paths`, and `job_required_documents`, plus code lookup tables.

**Consequences.** The app can keep fast tables while gaining accurate maps, filters, eligibility views, and future scoring features. Existing imports continue to work, but broad imports should wait until the child-table schema lands.

---

## ADR-0014 - Recommendations are deterministic and explainable before embeddings
Date: 2026-05-05
Status: Accepted

**Context.** Phase 6.5 adds preference feedback and similar-job suggestions, but V3 AI/RAG work is intentionally deferred until the relational data pipeline is stable.

**Decision.** Similar-job recommendations are generated locally from structured fields, parsed text themes, tags, and explicit feedback. Every suggestion stores exact factors in `job_recommendations.factors_json`, and negative feedback can suppress or down-rank matching jobs.

**Consequences.** Recommendations are auditable, testable, and cheap to run. They are less semantically rich than embeddings, but they keep V1/V2 behavior transparent and give the later vector layer a clean feedback history to learn from.

---

## ADR-0015 - OPM ingestion is file-based and source-labeled
Date: 2026-05-05
Status: Accepted

**Context.** OPM workforce data is distributed as large downloadable files, not as a transactional API like USAJOBS. The app must keep workforce counts, accessions, and separations analytically separate from USAJOBS postings.

**Decision.** V1 imports OPM/FedScope CSV, TSV, Excel, or ZIP files through `src/opm_data.py` into `opm_workforce_records`. State maps expose an explicit source switch: "USAJOBS postings" or "OPM workforce", with separate OPM metrics for employment, accessions, and separations.

**Consequences.** The app can ingest downloaded OPM files without adding a network downloader or scheduler. Charts remain plainly labeled, avoiding posting-versus-hire confusion. More precise OPM field mapping can be added as real source files reveal additional column variants.

---

## ADR-0016 - Public map tool is a separate sibling product, not a dashboard feature
Date: 2026-05-06
Status: Accepted

**Context.** The local dashboard (ADR-0001) is intentionally local-first, single-user, no cloud, no FastAPI/React. A separate public-facing job-search map at `thegrandpipeline.com/map` was requested. Treating it as a dashboard feature would silently invalidate ADR-0001's hosting and stack rules; treating it as a separate product preserves both products' constraints.

**Decision.** The public map lives in a new `public_map/` subdirectory with its own SvelteKit app, its own `package.json`, and its own deploy target (Cloudflare Pages). The data flow is one-way and read-only: a Python script (`scripts/export_public_map.py`) reads the local SQLite database, writes static GeoJSON/JSON snapshots to `public_map/static/data/`, and a nightly `git push` triggers a Cloudflare Pages rebuild. No live API, no auth, no DB online, no user data. Stack: SvelteKit (static adapter) + Mapbox GL JS + Cloudflare Pages. The Mapbox token is restricted by URL referrer to `thegrandpipeline.com` and `*.pages.dev` so a leaked bundle token cannot be reused elsewhere.

**Consequences.** ADR-0001 still applies to the dashboard; the public map is the documented exception. ADR-0002's "postings â‰  hires" rule applies to the public map's UI just as it does to the dashboard â€” the optional OPM overlay must be labeled "federal workforce, not postings." ADR-0008's "no automated applications" rule still holds: the public map only links out to canonical USAJOBS URLs. Future migrations (Postgres, FastAPI) remain optional and would happen on the dashboard side; the public map's read-only static contract is unaffected.

---

## ADR-0017 - Public map uses a layered, zoom-driven interaction model with a maxzoom cap
Date: 2026-05-06
Status: Accepted

**Context.** USAJOBS publishes city-level locations, not duty-station addresses. The original V1 plan called for cluster markers at all zoom levels, which would imply street-level precision the data does not have. Separately, the user wants meaningful low-zoom analysis (state and locality stats), not just markers â€” and a way to surface "where does my paycheck go furthest" more directly than a list of jobs.

**Decision.** The public map presents a layered, zoom-driven view with a hard **maxzoom of 9** (metro level):

- Zoom 3â€“5: state choropleth with a user-selectable metric (postings, workforce, accessions, separations, remote share, pay-vs-COL).
- Zoom 5â€“7: locality pay area outlines fade in over the choropleth.
- Zoom 7â€“9: county and CBSA outlines plus emerging marker clusters.
- Zoom 9 (cap): individual job markers at city centroid. The map never zooms past 9.

Every marker carries a `geo_quality` flag (`source`, `city`, or `state_centroid`, in priority order — `source` means lat/lon came directly from the USAJOBS Search payload via `job_locations.latitude/longitude`; the other two are SimpleMaps geocode fallbacks) which the UI surfaces. The flagship choropleth metric is **pay-vs-cost-of-living ratio** = locality-adjusted pay Ã· BEA Regional Price Parity, expressed as a number where 100 = national average. State, locality, county, and marker layers are all clickable with their own popups.

**Consequences.** The map is honest about precision. The state/locality/county roundup popups become a primary feature, not an afterthought. The choropleth metric switcher requires a robust reference-data layer (pay tables, COL, polygons) â€” see ADR-0018. The 9-zoom cap also has a side benefit: the polygon GeoJSON files don't need high-resolution geometry, keeping the public bundle small.

---

## ADR-0018 - Reference data is local-first and admin-managed, with per-source status tracking
Date: 2026-05-06
Status: Accepted

**Context.** The public map needs annual data from at least four federal sources (OPM pay tables across many pay plans, OPM locality definitions, Census TIGER polygons, BEA RPP) plus a third-party COL backup. The user has stated the bar is "exquisite" â€” pay data accuracy is non-negotiable â€” but is the sole operator and not a software engineer. Bad imports must be detectable, and manual override must be available when an automated source breaks or is wrong.

**Decision.** Every external dataset has a row in a new `data_source_status` table with a stable `source_key`, display name, category, last run / success / error timestamps, row count, manual-override flag, and notes. A new local-only Streamlit page (`pages/11_Public_Map_Admin.py`) renders this table and provides per-source actions: refresh now, upload override, view recent diff. Every ingest script writes its result back to `data_source_status`. The admin page is part of the dashboard's `pages/` tree and never appears on the public site.

Every pay-scale row also stores its `source` and `source_url` so the public site (and the admin diff view) can attribute and audit individual values. Pay plan support starts with GS and Federal Wage System (largest by headcount) and adds others incrementally; the admin page makes it obvious which plans are present, stale, or missing.

**Consequences.** The user can self-verify every dataset before a public deploy â€” the dashboard's diff view shows year-over-year changes on pay tables so an import bug is visible before nightly snapshots reach the CDN. Manual overrides give an escape hatch when an automated source breaks or is wrong. The freshness UI in the public footer reads from the same status table, so what the user sees in admin matches what the public sees about provenance.

---

## ADR-0019 - Locality pay polygons: OPM ArcGIS FeatureServer primary, county-dissolve fallback
Date: 2026-05-06
Status: Accepted

**Context.** Locality pay areas are defined annually by OPM at the **county** level (5 CFR 531.603). Polygons must be drawn somehow. Options: (a) the public OPM ArcGIS Online FeatureServer at `services1.arcgis.com/cc7nIINtrZ67dyVJ/.../Locality_Pay_Areas/FeatureServer/1` (publicly queryable polygon layer, JSON, owner is a third-party publisher); (b) dissolve Census TIGER county polygons by OPM's annual county FIPS membership list. Each has trade-offs.

**Decision.** Use both. The OPM ArcGIS FeatureServer is the **primary fast-bootstrap source** because it ships ready-to-use polygon geometry. OPM's annual county-FIPS definition list is the **canonical membership source** because it is the legal definition of the boundaries. The ingest pipeline:

1. `scripts/ingest_locality_definitions.py` pulls OPM's per-locality county FIPS list. This is what `locality_pay_counties` stores; it is the source of truth for membership.
2. `scripts/ingest_locality_polygons.py` tries the OPM ArcGIS FeatureServer first; on failure (service down, schema change, wrong year), it falls back to dissolving Census TIGER county polygons keyed by `locality_pay_counties` from step 1.
3. Both paths write to `locality_pay_areas.polygon_path` (a file under `data/external/`) and update `data_source_status` so the admin dashboard reflects whichever path produced the current polygons.

**Consequences.** The public map ships fast in V1 thanks to the FeatureServer. If that service moves, disappears, or drifts from OPM definitions, the dissolve fallback keeps the site working without code changes. The county-FIPS table doubles as the join key that maps any (city, state) job location â†’ county â†’ locality, which the pay calculator already needs.
## ADR-0020 - USAJOBS map favors real work-location coordinates
Date: 2026-05-06
Status: Accepted

**Context.** The user needs to zoom into actual work locations, not only see state totals. USAJOBS Search can return latitude and longitude inside `PositionLocation`; HistoricJoa commonly returns city/state/country. Neither endpoint should be treated as a reliable street-address source.

**Decision.** Store `job_locations.latitude` and `job_locations.longitude` when observed. The USAJOBS map is a Folium-based GIS-style map with detailed street/imagery base layers. It uses only real coordinates for work-location points, lets the user include/exclude multi-location postings, and shows remote-anywhere plus current non-remote postings without coordinates in tables only after the user zooms into the map.

**Consequences.** Current Search imports can produce zoomable point maps. Historic-only slices may still show mostly state-level maps until coordinate data is present. We avoid fake precision by not silently geocoding city/state-only records. Detailed behavior and reusable replication guidance live in `docs/MAP_FEATURE_SPEC.md`.

---

## ADR-0021 - Application tracker is manual and local
Date: 2026-05-06
Status: Accepted

**Context.** The user needs application follow-through: resume version used, submission/reference IDs, referral/interview/outcome dates, next actions, contacts, and notes. This can make the dashboard much more useful without crossing into automated application behavior.

**Decision.** Add local `applications` and `application_events` tables with a Streamlit Application Tracker page. Tracker status can sync the matching `saved_jobs.status` value for Applied/Referred/Interview/Selected/Not selected, but all fields are user-entered or locally derived. The app does not submit applications, fill agency forms, or authenticate to USAJOBS.

**Consequences.** The user gets a practical pipeline view and event history while preserving ADR-0008. Future resume-version management may link file labels or local metadata to these rows, but no resume parsing is required for this phase.

---

## ADR-0022 - Resume versions are metadata-only in V2
Date: 2026-05-06
Status: Accepted

**Context.** The application tracker needs to know which rÃ©sumÃ© package was used, but full rÃ©sumÃ© parsing belongs with the later AI/RAG work and should not be mixed into the local CRUD tracker.

**Decision.** Add a `resume_versions` table and Streamlit page for labels, filenames, local paths, target series/grade, active/archive status, and notes. The Application Tracker can select an active label, but the app does not upload, parse, score, or rewrite rÃ©sumÃ© content in V2.

**Consequences.** Application records become more consistent without introducing sensitive-document processing. V3 can later add rÃ©sumÃ© parsing against this metadata boundary.

---

## ADR-0023 - Repost detection is deterministic and review-oriented
Date: 2026-05-06
Status: Accepted

**Context.** Reposted announcements are useful career intelligence, but title reuse and recurring hiring actions can look similar without being the same administrative announcement.

**Decision.** Add a local deterministic repost detector that blocks by agency and series, then compares normalized titles and long-form text hashes. Results are persisted in `repost_runs`, `repost_groups`, and `repost_group_members` with evidence JSON. Repost alerts use persisted groups when available.

**Consequences.** The user gets auditable possible-repost groups without opaque AI or overclaiming certainty. Thresholds may need tuning as more real data accumulates.

---

## ADR-0024 — Public-map UI invariants (course correction Phase D.5)
Date: 2026-05-07
Status: Accepted

**Context.** Phase D shipped a working filter panel and choropleth metric switcher. User review on 2026-05-07 found that the agency filter is a free-text box (so "FEMA" silently substring-matches across multiple fields), there's no way to save a filter set, no way to zoom to an address or ZIP, panels overlap at common viewport sizes, the heat of postings disappears at low zoom, clicking a state opens a popup but does not zoom in, and several choropleth metrics paint nothing because the underlying data is empty. The design problem is not "add features" — it is "stop pretending data exists when it doesn't" while also closing the UX gaps the user actually expects from a map.

**Decision.** The public map adopts thirteen invariants codified in `CLAUDE.md` under "Public Map V1.5 invariants." They cover: agency multi-select with code-backed typeahead and aliases (no free-text agency filter); first-class saved searches in `localStorage`; address / ZIP geocoder with Mapbox primary + Nominatim fallback + offline ZIP centroids; persistent posting heat layer at every zoom; click-state-to-fit-bounds; a metric switcher that declares each metric's `status` (`ready` / `wip` / `under-construction`) and only colors the map when the metric is `ready`; a fixed UI layout grid (`public_map/src/lib/layout.ts`) so panels never overlap; a corpus growth path so the map has enough data to be useful; an OSM fallback that actually boots without a Mapbox token; and a closed-postings overlay for trailing-90-days context. The implementation queue is Phase D.5 of the public-map plan.

**Consequences.** ADR-0017's layered, zoom-driven model is unchanged, but D.5 fills in the layers that Phase D left empty. ADR-0018 still governs how reference data is tracked and refreshed; D.5 adds new sources (ZIP centroids, agency aliases, ACS county rent, optional BLS CPI) under the same status-tracked pattern. Public-map V1 is **not** done until every D.5 invariant is satisfied; Phase E (deploy) is paused until then. The Mapbox basemap remains primary, but if mapbox-gl v3 cannot reliably boot the OSM fallback, ADR-0026 captures a swap to MapLibre GL JS.

---

## ADR-0025 — Federal Real Property layer
Date: 2026-05-07
Status: Accepted

**Context.** USAJOBS postings answer "where could I work?" but not "where is the federal government already?" Visualizing federal infrastructure alongside open postings gives applicants a sense of agency footprint, lets them spot duty-station clusters, and lights up agency-specific patterns ("FEMA is hiring near FEMA buildings"). The GSA Federal Real Property Profile (FRPP) is the canonical, federally-published, public-domain dataset for this.

**Decision.** Add a `federal_properties` table and a parallel ingest script (`scripts/ingest_federal_properties.py`) tracked under `data_source_status` source key `gsa_frpp`. The public-map exporter emits `federal_properties.geojson`; the SvelteKit client renders federal properties as small neutral diamonds at zoom ≥ 6 with their own popup component. Agency chip filters apply to both jobs and properties so users can compare hiring against the existing footprint. Disposed and non-georeferenced FRPP rows are dropped at ingest; missing-county-FIPS rows are filled via `zip_centroids` when possible.

**Consequences.** Adds one schema-bumping table and one tracked external dataset, both following the ADR-0018 pattern (admin-managed, status-tracked, manual override available). The map's bundle grows by ≈ 2–3 MB gzipped (≈ 110 K active georeferenced rows after filtering). FRPP refresh is annual, low-effort. If FRPP moves or is paywalled, the fallback documented in `docs/PUBLIC_MAP_DATA_SOURCES.md` is USA.gov "Where the Federal Government Has Buildings."

---

## ADR-0026 — MapLibre GL JS swap *(reserved, not yet invoked)*
Date: 2026-05-07
Status: Proposed

**Context.** The OSM raster fallback in `public_map/src/lib/basemap.ts` has been brittle under `mapbox-gl` v3 because the runtime expects a real access token even for non-`mapbox://` sources, and the default `glyphs:` URL points at `fonts.openmaptiles.org` which often returns 401. D.5.8 hardens the configuration; if those steps don't reliably keep the no-token path working across the lifetimes of `mapbox-gl` versions we'll ship, the ergonomics of supporting both paths get expensive.

**Decision.** *(Pending — invoked only if D.5.8 cannot stabilize the no-token path.)* Replace `mapbox-gl` with `maplibre-gl` for the public map. MapLibre is a community-maintained fork with a near-identical JavaScript API, no token requirement, and full support for both Mapbox-style sources (with a Mapbox token) and arbitrary tile sources (without one). The dashboard does not depend on `mapbox-gl`, so the swap is contained to `public_map/`.

**Consequences.** Mapbox vector tile rendering would still require a token; MapLibre treats the token as a per-source configuration rather than a global. Some Mapbox-hosted styles (`mapbox://styles/...`) would need to be replaced with self-hosted style JSON or transpiled. We'd lose Mapbox-only features like 3D Standard buildings, but the public map already declines those (maxZoom 9). Decision will be re-evaluated at the end of D.5.8.

---

## ADR-0027 — Self-bootstrapping ingests
Date: 2026-05-07
Status: Accepted

**Context.** The orchestrator `scripts/refresh_public_map_data.py` was designed so each ingest step is gated by an environment variable that points at a pre-downloaded local file (e.g., `PUBLIC_MAP_STATE_GEOJSON`). That made sense during early development when datasets were being audited by hand, but it means a clean checkout of the repo cannot produce a complete public-map bundle without the operator first downloading and exporting six environment variables. The cost: a fresh map with empty polygon layers and a "color states by" switcher with nothing to color. The user verified this on 2026-05-07.

**Decision.** Every public-map ingest script must run successfully from a clean checkout with no environment variable set. Each script defaults to one of three sources, in priority order:

1. **A canonical public URL.** Census TIGER cartographic boundary ZIPs, BEA Regional Price Parities CSV, OPM published GS pay XML/CSV. The script downloads it on first run, caches it under `data/external/<source_key>/<vintage>/`, and reuses the cached file thereafter.
2. **A small curated CSV checked into the repository.** For sources that publish only HTML pages with no stable machine-readable artifact (currently OPM locality area definitions and OPM annual locality pay percentages), the operator commits a curated CSV under `data/external/<source_key>/<year>.csv`. Files are public-domain and small (a few KB each).
3. **An operator-supplied path via `--input` or an environment variable.** This becomes an *override* — it never gates whether a step runs.

The orchestrator's `build_steps()` enables every supported source by default. `--skip <key>` remains the only way to disable a step. The "ENABLED / SKIP" status now reflects the operator's choice, not whether they remembered to set six env vars.

**Consequences.** A fresh checkout produces a complete bundle in one command. The repository grows by a few hundred KB of seed CSVs (annual OPM definitions and locality pay) - small enough to check in, large enough to keep the ingest scripts honest. `requirements.txt` gains `pyshp` for shapefile-to-GeoJSON conversion without a GDAL system dependency. ADR-0018's per-source status tracking is unchanged: every run still writes to `data_source_status` so the admin page reflects what actually happened, regardless of which source path was used. Operators who prefer fully manual control still can: `--input` and the env vars override the default behavior.

---

## ADR-0028 - Public-map scoped search, 2026 pay, and personal compensation comparison
Date: 2026-05-08
Status: Accepted

**Context.** Follow-up public-map review added requirements: the GS pay reference must move to 2026; polygon clicks should snap to the selected geography; state/locality/future-city windows need scoped search actions, remote inclusion, Add to Search, and a with/without-global-filters preview; the app needs light and dark mode; users need to enter expected grade/locality or custom wage for cost-of-living comparison; listings need urgency/fill badges when source data supports them; and job listings need Autotrader-style local state for viewed, saved, and hidden jobs.

**Decision.** Public-map V1.5 expands the invariant set and Phase D.5 queue. Official 2026 GS base/locality tables become the required public reference year. Geographic search becomes an additive filter model using `geoScopes` chips, where multiple selected geographies are ORed together and ANDed with non-geographic filters. Polygon action windows can temporarily ignore global filters for preview without mutating the global search. Light/dark theme is a persisted first-class UI setting. Compensation comparison is a sourced calculation feature: it accepts GS grade/step/locality or a custom wage and emits COL-adjusted equivalent-pay statements with source/precision labels. Job urgency/fill badges are source-backed only, using close dates, openings, and USAJOBS-provided application-count fields when available; no scraping or invented applicant counts. Viewed/saved/hidden job state is stored in a local browser profile using localStorage or IndexedDB. Hiding a job excludes it from map markers, heat inputs, job lists, and scoped-search counts by default, while the local profile keeps Saved Jobs, Hidden Jobs, and viewed jobs that have closed recoverable.

**Consequences.** D.5 grows by six sub-phases: D.5.14 through D.5.19. The exporter will need new payload fields for `reference_year`, compensation reference data, urgency/fill signals, and stable job identity for local profile state. The Svelte app will need `GeoScopeWindow`, theme persistence, a compensation comparator, and a local profile/jobs-state module. This does not add public-map accounts, authentication, cloud sync, or a backend. Public-map V1 is not done until these features are documented, tested, and reflected in `CLAUDE.md`, `docs/PRODUCT_SPEC.md`, `docs/ROADMAP.md`, and the detailed Claude plan.

---

## ADR-0029 — Edge-cached on-demand historic via Cloudflare Pages Functions
Date: 2026-05-09
Status: Accepted

**Context.** The original D.5.21 / D.5.22 plan called for a per-job History tab and a posting timeline sparkline backed by a bulk HistoricJoa import (millions of records, ~6.8 GB raw, ~15 hours per the 2026-05-09 recon). That bulk pull breaches every threshold in `config.py` and bloats the dashboard's local SQLite without much user-facing payoff: any given session uses only a tiny slice of the corpus. The user proposed (2026-05-09) a lazy alternative: when a visitor clicks "Posting Intelligence" on a JobCard, perform a targeted API call for that filter set and cache the result. ADR-0016 said "no live API" for the public site, but a read-only edge-cached proxy to a public, key-less endpoint is qualitatively different from "DB online" or "user data online."

**Decision.** Add a Cloudflare Pages Functions endpoint at `public_map/functions/api/job-history.ts` that proxies USAJOBS HistoricJoa with edge caching. Contract:

- Request: `GET /api/job-history?position_id=…&agency_code=…&series=…&grade=…&state=…&months=…&window=1mo|3mo|6mo|1yr|3yr|5yr|10yr`
- Server-side: builds the equivalent HistoricJoa query (HistoricJoa is public, no API key required per CLAUDE.md), strips long text fields from the response to keep payload small, and returns a trimmed JSON.
- Cache: `caches.default.put(...)` with a 24-hour TTL keyed by the exact query. First request pays ~1–3 s round-trip; every subsequent request globally is served from edge cache.
- Failure mode: HistoricJoa downtime → returns `{status: 'unavailable', retry_after: 3600}`; the JobCard renders an explanatory message, never a fake-history fallback.
- The Svelte client treats the endpoint as click-to-load only (per user decision 2026-05-09). No prefetch, no autoload on JobCard mount. This keeps cache size and outbound API load proportional to actual user intent.

The bulk-historic plan (D.5.7's HistoricJoa half + D.5.21 static history JSON + D.5.22 timeline pre-compute) is **rejected**. The trailing-90-day closed-jobs overlay stays a static export because it's used for the gray-dots layer at every page-load, not per-job.

**Consequences.** ADR-0016's "no live API" clause is narrowed to: "no live API that requires keys, no live DB, no user data online." Public, keyless endpoints behind an edge cache are allowed for explicit click-to-load features. The dashboard's local SQLite stays small (no millions of HistoricJoa rows). Adds one Cloudflare Pages Function (free tier covers ~100k req/day) and one new ROADMAP entry, **D.5.24 — On-demand Posting Intelligence**. The on-demand tab eventually replaces D.5.21 (per-job history) and D.5.22 (timeline sparkline) — both are folded into D.5.24. The trailing-90-days closed-jobs overlay (D.5.7's static half) is unchanged.

---

## ADR-0030 — 2026 GS pay-table cutover with bootstrap seed + operator verification
Date: 2026-05-09
Status: Accepted

**Context.** CLAUDE.md invariant 15 requires Public Map V1 to ship official OPM 2026 GS base + locality pay rows, with `manifest.json.reference_year` resolving to 2026 and the Public Map Admin spot-check verifying sampled cells against OPM-published values. The OPM website is not reliably reachable from every dev sandbox (the 403 responses observed during the D.5.14 work are an example), so a "fetch official PDF at code time" approach can leave a clean checkout unable to bootstrap the 2026 reference year. We needed the cutover to be unblockable while still preserving the official-data invariant.

**Decision.** D.5.14 ships a two-stage cutover:

1. **Bootstrap seed (now).** Check in `data/external/opm_gs_pay/2026_base.csv` computed as `round(2025_rate × 1.010)` — the across-the-board portion of the 2026 raise per OPM's published PDF title "Incorporating the 1% General Schedule Increase." Locality percentages (`opm_locality_pay/2026.csv`) and county→locality mappings (`opm_locality_definitions/2026.csv`) carry the 2025 values forward as 2026 placeholders, since both are stable year-over-year. `SEED_CSV` constants in the three OPM ingest scripts point to the 2026 files; the orchestrator label changes from "2025 seed" to "2026 seed". `current_reference_year(conn)` therefore resolves to 2026 immediately on a clean checkout.

2. **Operator verification (before V1 deploy).** `pages/11_Public_Map_Admin.py` gains a "Reference year (D.5.14)" panel that shows three sampled GS cells (GS-1 step 1 base, GS-13 step 1 base, GS-15 step 10 base), the resolved reference year, and the official OPM 2026 PDF URL. Any operator with internet access opens the PDF, checks the three cells, and either accepts the seed (cells match within $1) or replaces `data/external/opm_gs_pay/2026_base.csv` with the verified rows and re-runs `python scripts/ingest_gs_pay.py`. The existing year-over-year diff already flags large unexpected jumps. V1 is **not** callable done until an operator has logged a clean spot-check against OPM's published 2026 values.

**Consequences.** Public-map exports always have a populated reference year, even before the operator can reach OPM directly. The bootstrap seed is clearly labeled with `source_url=https://www.opm.gov/.../2026/general-schedule/` and the seed CSV is not used as final V1 data — D.5.14 is marked partial in `docs/ROADMAP.md` until the operator verification step is logged. `pay_calculator.calculate_job_pay_table` works against the 2026 rows the same way it worked against 2025, so D.5.11 (per-job pay grid with status flag) inherits the 2026 cutover automatically. If the rounding rule in OPM's actual PDF differs from `round(rate × 1.01)` for a given cell (annual rates derive from hourly × 2087, with their own rounding chain), the diff will be at most a dollar or two per cell — the spot-check tolerance is set so that anything outside ±$1 fires.

---

## ADR-0031 — County-level COL via ACS rent ratio applied to BEA state RPP
Date: 2026-05-09
Status: Accepted

**Context.** Public Map invariant 9 (CLAUDE.md "Cost of living layer goes deeper than state") and D.5.10 require county-level cost-of-living signal so CountyDetail and downstream consumers can reflect within-state variance. BEA does not publish a county-level Regional Price Parity — its smallest geography is CBSA. Census ACS 5-year table B25064 (median gross rent) is the canonical, public-domain, county-level economic signal that proxies COL well at small geographies. We need a method that (a) gives every county a defensible number, (b) reuses the BEA state RPP we already trust at the state level, (c) survives a clean checkout with no API calls, and (d) is honest about being an approximation.

**Decision.** Estimate county COL as a within-state rent-ratio scaling of the state RPP::

    county_col_index = state_rpp × (county_rent / state_median_rent)

where:

- `state_rpp` is the latest BEA `cost_of_living_index` row with `geo_type='state'` for the county's state (already loaded by `scripts/ingest_bea_rpp.py`).
- `county_rent` is the ACS B25064 5-year median gross rent for the county.
- `state_median_rent` is the median of the county rents present in the input file for that state. With a small input (e.g., the checked-in seed) this is the median across the bundled counties; with a full ACS pull it is the true median across all counties.

Implementation lands in `scripts/ingest_acs_county_rent.py`, which writes one `cost_of_living_index` row per county under `source='census:acs5_b25064'`, storing the derived index in `rpp_overall` and the raw ACS median rent (in dollars) in the `rpp_rents` slot. The unit overload of the `rpp_rents` column is documented inline and disambiguated by the `source` field — for `bea:rpp` rows `rpp_rents` is a 100-base index, for `census:acs5_b25064` rows it is a dollar amount. Per ADR-0027 the ingest is self-bootstrapping: it defaults to the checked-in seed at `data/external/census_acs_rent/2023.csv` and accepts an operator override via `--input` or `PUBLIC_MAP_ACS_COUNTY_RENTS_CSV`. The orchestrator runs the ACS step right after `ingest_bea_rpp` so the state RPP it depends on is in the database.

The exporter wires the county rows into `counties_geojson` via a new `_county_col_lookup`. Counties with an ACS row expose `rpp_overall_source='county'` plus the raw `rent_median`; counties without one fall back to the existing state RPP and expose `rpp_overall_source='state'`. The state RPP is always exposed as `rpp_state` so the InfoTooltip can show the multiplication. `cost_of_living()` payload gains a `by_county` bucket keyed by 5-digit FIPS for any future client consumer that wants the raw lookup.

**Consequences.** Every county the operator's input covers gets a directionally correct COL signal that beats the prior state-level fallback for county detail surfaces. The estimate is explicitly an approximation: counties get the state's overall RPP scaled by their rent ratio relative to other counties in their state. Within a state with low rent variance the index hardly differs from the state RPP; within high-variance states (CA, NY, TX) the index meaningfully reflects the difference between expensive and cheap counties. CountyDetail surfaces the formula inline so users can see the chain. BLS metro CPI (the optional secondary signal in PUBLIC_MAP_DATA_SOURCES.md) is deferred — V1 ships with rent-as-COL-proxy and revisits CPI later if rent-only is insufficient. Replacing the seed with a full ACS county pull is a single CLI step (`python scripts/ingest_acs_county_rent.py --input <census_pull.csv>`); operators with a Census API key can fetch the data via the documented URL pattern and convert the JSON-array response to the simple CSV the script expects. Because the unit semantics of `rpp_rents` differ across sources, anything reading `cost_of_living_index` for that column must check the `source` column too — that contract is documented in CLAUDE.md, in `cost_of_living()`, and in `_county_col_lookup`.

