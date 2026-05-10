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
Status: Superseded by ADR-0031 (narrowed, not reversed)

**Context.** The application tracker needs to know which rÃ©sumÃ© package was used, but full rÃ©sumÃ© parsing belongs with the later AI/RAG work and should not be mixed into the local CRUD tracker.

**Decision.** Add a `resume_versions` table and Streamlit page for labels, filenames, local paths, target series/grade, active/archive status, and notes. The Application Tracker can select an active label, but the app does not upload, parse, score, or rewrite rÃ©sumÃ© content in V2.

**Consequences.** Application records become more consistent without introducing sensitive-document processing. V3 can later add rÃ©sumÃ© parsing against this metadata boundary.

**Update 2026-05-10 (ADR-0031).** This ADR is narrowed, not reversed. The "no auto-parse / no auto-score / no auto-rewrite" boundary still holds for every in-app flow. ADR-0031's LLM Project Export is the one exception: it copies user-selected résumé file(s) verbatim into a bundle the user explicitly downloads. The dashboard itself still does not parse résumé contents.

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

## ADR-0031 — LLM Project Export is a vendored, GovJobs-specific feature
Date: 2026-05-10
Status: Accepted
Supersedes: ADR-0022 (résumé content boundary)

**Context.** A sibling tool, `Fileslicer` (a.k.a. `llm_project_packer`), already produces project-context bundles (Markdown bundles + manifest + per-target instructions) for ChatGPT Projects, Claude Projects, generic chats, and RAG. The user wants a similar capability inside GovJobs — but specialized for job hunting: each saved job rendered with structured fields, scoring, hiring-climate signals, locality-adjusted pay, and a cost-of-living block; the user's actual résumé file(s) bundled in; one-click drop-in for Claude Projects or ChatGPT Projects with pre-built instructions. The eventual goal is a knowledge assistant inside the dashboard, but that is explicitly out of scope here.

Two integration paths were considered: (a) `pip install -e ../Fileslicer/llm_project_packer` and import `run_packaging_job` directly, or (b) vendor a small, GovJobs-specific export pipeline. The user chose (b): the GovJobs export must be lean (no repair-manual / FEMA-policy / generic-RAG modes), domain-specialized (résumé + jobs + COL + OPM trend + closing-window in one bundle), self-contained (no external repo coupling), and trust-forward (privacy notice baked in, vendor-curated tier presets that the user can override). FileSlicer's CLAUDE.md hard rule "Token presets are packaging targets, not official platform context-window limits" is preserved verbatim in spirit — we surface tier numbers as guidance, dated, and editable.

ADR-0022 explicitly forbade parsing or copying résumé content in V2. That boundary made sense for the in-app Application Tracker but blocks the killer feature of this export (résumé + jobs reasoned together by the LLM). ADR-0022 is superseded for the narrow case of user-initiated exports: the dashboard never auto-parses, scores, or rewrites résumés; the export pipeline only copies user-selected résumé files into a bundle the user explicitly downloads.

**Decision.**

1. **Vendor a `src/llm_export/` package.** Port the small useful pieces of FileSlicer's `bundler.py` and `manifest.py` (token-budget bundling, `DOC_xxxx` identity headers, three-format manifest) into GovJobs. Attribute the origin in module docstrings. Do not depend on FileSlicer at runtime. The two products evolve independently.
2. **Two-target scope only — Claude Project and ChatGPT Project.** No NotebookLM target (per user). A `generic` target for one-off chats is shipped for free since it's near-zero extra work.
3. **Tier presets are user-editable, dated, and labeled as guidance.** A `data/llm_tiers.json` (or small SQLite table) ships with current Claude Pro / Claude Max / ChatGPT Plus / ChatGPT Pro / ChatGPT Team caps as of the export's release date. Every knob (file count, MB total, max tokens per bundle) is editable by the user via Settings. Built-in label includes a "Verified: YYYY-MM-DD" stamp so the user knows when to revisit.
4. **Preflight ingestion is in scope.** When the export needs HistoricJoa slices for closing-window stats or OPM workforce data for hiring-climate trends, the pipeline performs targeted USAJOBS API calls before assembling the bundle, persists results to SQLite per the existing `import_manifests` / `data/raw/` pattern, and caches each slice with a 7-day freshness window. A user-visible time ceiling (default 5 min, configurable) stops the export from stalling on a wide filter; jobs whose history could not be fetched in time render with an honest "insufficient history" note.
5. **Filter-export volume gate.** A current-filter export that exceeds the chosen tier's file count is trimmed to the top-N by score, with the ranking explained in the manifest. The user is shown the trim before running.
6. **Privacy notice is first-class.** The export modal, the `00_PRIVACY.md` file in the bundle, and the `00_START_HERE.md` instructions all state plainly: "uploading this bundle puts your résumé and saved jobs in the LLM vendor's hands; their privacy policy applies." A "résumé removed" mode is offered alongside the default for users who don't want to share their résumé.
7. **ADR-0022 narrowing.** The "metadata only" rule for résumés in V2 still applies *inside the dashboard* (the app does not auto-parse, score, or rewrite résumé contents in any UI flow). It does **not** apply to the LLM Project Export, which copies user-selected résumé files verbatim into a bundle the user explicitly downloads. The ADR-0022 record is preserved as historical context.

**Consequences.** GovJobs gains a domain-specialized export that does not exist in FileSlicer, without taking on a cross-repo dependency. The résumé content boundary moves from an absolute prohibition to a "no auto-processing in app, yes user-initiated export" posture. The hiring-climate and closing-window signals shipped here lay the data foundation for the future knowledge assistant (V3+) without committing to any of its design. The single new external risk is preflight-ingestion rate-limit budget; the time ceiling, freshness window, and `import_manifests` reuse keep it bounded.

The full design — staging-folder layout, instruction templates, tier-preset semantics, preflight-ingestion contract, and Phase 1–3 implementation queue — lives in `docs/LLM_EXPORT_SPEC.md` and the corresponding ROADMAP entry (Phase 12).

---

## ADR-0032 — Per-plan pay resolution strategy
Date: 2026-05-10 (revised same-day)
Status: **Proposed — not yet scheduled; needs further discussion before implementation**
Amends: CLAUDE.md hard rule 10 (no-widen guard binds immediately; per-plan rendering is target direction, not current behavior)

**Revision note (2026-05-10).** This ADR is **not a green-light to build**. The user's intent on revisiting it: (a) capture the design direction so the no-widen guardrail can bind today even though no implementation work is scheduled, (b) record the locality reality (~75% of postings live on the OPM 58-area grid, not the ~53% the audit's GS-only count suggested), and (c) park a new "Locality-Pinned View" tool concept for future discussion. Status is Proposed. Items 1–6 below are the proposed taxonomy and consequences; items 7–9 are the revision additions; the "Deferral schedule" is rewritten so that nothing in this ADR ships before V1 is callable done. Open questions at the end must be settled before sequencing.

**Context.** Rule 10 was originally written as "every posting has an exact pay table," which silently assumed GS-family pay. A `SELECT pay_plan, COUNT(*) FROM jobs GROUP BY pay_plan` against the live SQLite returned a top-30 distribution in which GS-family is only ~53% of postings. The other ~47% spans pay systems with structurally different rules:

- **FWS** (`WG`/`WS`/`WL`, ~11%) uses 248 wage areas anchored on military bases / VAMCs — geometry that does not match the 58 OPM GS locality areas. The Jan 2025 OPM final rule begins aligning the two maps but only for ~10% of the FWS workforce in this round; convergence is slow.
- **Non-Appropriated Fund** (`NF`/`NA`, ~11%) is its own pay system, set per local NAF instrumentality (MWR, exchanges, Marine Corps recreation). Not GS, not FWS, not OPM-published. The current `pay_plans` seed does not register it at all.
- **Title 38 VHA** (`VM` physician/dentist market pay, `VN` nurse facility panels, ~8%) is facility-level. `VN` is registered; `VM` — the larger of the two and the 4th-largest plan in the live data — is not.
- **Broadband / demo** (`NH`/`NJ`/`NK` AcqDemo; `IC`/`IH`/`IA` DCIPS; `FV`/`FG`/`AT` FAA Core Compensation; `SV` TSA; `CY` DoD Cyber Excepted Service; `ND` Navy demo; `ES` SES; ~14%) has ranges, not steps. None except `ES` are in the seed. `CY` is the 6th-largest plan in the live data.
- **Administratively determined** (`AD`, ~3%) and uniformed services (`CC` USPHS/NOAA Commissioned Corps) have no published civilian pay table at all.

The previous behavior — universal table lookup against `pay_scales` keyed by `(pay_plan, year, grade, step, locality_code)` — produces three failure modes for the non-GS half of postings: (a) `unavailable` status pinned on plans that *will never have* a table, indistinguishable from GS-family ingestion gaps; (b) `approximated` math derived from base × GS locality % for plans where GS locality is the wrong geography or no geography; (c) the temptation to "just add some rows" to `pay_scales` for FWS, Title 38, or broadband plans, which would silently corrupt the table by stuffing wage-area rates under fake locality codes or fabricating `step=0` rows for stepless plans.

**Decision.** Every `pay_plans.code` is assigned exactly one `pay_resolution_strategy`. The pay_calculator, the public-map exporter, and the JobCard renderer all dispatch on that strategy. Six strategies cover the live-data top 30 and provide a typed "unknown / posting-only" fallback for codes that show up later.

1. **Strategy taxonomy.**

   | Strategy | Card behavior | Geography model |
   |---|---|---|
   | `gs_table` | Full grade × step locality-adjusted table from `pay_scales`. Status pills `exact` / `approximated` / `unavailable` keep their D.5.11 meaning. | OPM GS locality area |
   | `range_only` | Statutory range or broadband min/max for the year from a per-plan range source, or the posting's `salary_min` / `salary_max` when no published range exists. Labeled "no step structure." | None or GS locality cap (plan-specific) |
   | `wage_area_deferred` | Posting salary + "Federal Wage System — wage area not yet modeled in V1" note. **No GS locality stamp. No GS adjustment math.** | FWS wage area (Phase 13) |
   | `facility_market` | Posting salary + plan name + a one-line link to the canonical schedule (VA OCHCO for VHA; State Department for Foreign Service). No fabricated table; no GS locality stamp. | VA facility / FS post |
   | `admin_determined` | Posting salary only with "Agency-determined; no published table." | None |
   | `unmodeled` | Posting salary only with "Pay system not modeled" + the raw plan code, so the operator can register it. | None |

   The `unavailable` status is reserved for `gs_table` postings that should have a table but don't yet — never for plans on a different strategy.

2. **Plan → strategy table** (seeded into `pay_plans.pay_resolution_strategy`; the table is the V1 contract, not exhaustive of every OPM pay plan code):

   | Strategy | Plans |
   |---|---|
   | `gs_table` | `GS`, `GM`, `GL`, `GP`, `GR`, `GG`, `GW`, `LE`, `AL` |
   | `range_only` | `ES`, `SL`, `ST`, `EX`, `NH`, `NJ`, `NK`, `ND`, `IC`, `IH`, `IA`, `FV`, `FG`, `AT`, `SV`, `CY`, `NF` |
   | `wage_area_deferred` | `FW`, `WG`, `WL`, `WS`, `NA` |
   | `facility_market` | `VN`, `VM`, `VP`, `FO`, `FP`, `CC` |
   | `admin_determined` | `AD` |
   | `unmodeled` | (default for any code present in `jobs.pay_plan` but absent from `pay_plans`) |

   `NF` (NAF salaried bands) is classed `range_only` because the NAF pay-band structure publishes per-band ranges; `NA` (NAF wage grade) is classed `wage_area_deferred` because it follows the NAF wage-area survey model. Both will be revisited if the audit shows enough volume to justify a dedicated NAF strategy.

3. **Registration discipline.** Adding a code to `pay_plans` requires picking a strategy from the taxonomy above. The Public Map Admin page (`pages/11_Public_Map_Admin.py`) gains an "Unregistered pay plans" panel that shows `SELECT DISTINCT pay_plan FROM jobs WHERE pay_plan NOT IN (SELECT code FROM pay_plans)`. Codes there default to `unmodeled` until an operator registers them. Introducing a new strategy (a seventh kind) requires a follow-up ADR.

4. **The no-widen rule, codified.** `pay_scales` is for `gs_table` postings only.
   - No `step=0` rows for `range_only` plans.
   - No synthetic locality codes for `wage_area_deferred` plans.
   - No facility-level rates inserted under fake locality codes for `facility_market` plans.
   - No rows at all for `admin_determined` or `unmodeled`.

   Range-only plans get rate data, when published, in a separate `pay_ranges` table keyed by `(pay_plan, year, band_or_grade)` — *not* in `pay_scales`. FWS wage-area rates, if/when ingested, get their own `fws_wage_areas` + `fws_pay` tables in Phase 13. Title 38 facility panels and Foreign Service post differentials get their own per-plan tables when those phases land. PRs that grow `pay_scales` for non-`gs_table` plans must be rejected and the work routed.

5. **Choropleth scope.** The state / county pay-vs-COL choropleth and the GS-13 step 1 reference (`_gs_base_step1_for_year`, `_pay_vs_col`) remain anchored to GS-13 step 1 as the *reference cell* — but the polygon geometry (the 58 OPM locality areas) is the correct geography for every plan with `pay_area_kind = gs_locality` (see item 7). Tooltips and legends must say "GS-13 step 1, locality-adjusted" — not "federal pay" — and the legend must note "applies to ~75% of postings (GS-family + AcqDemo + DCIPS + FAA Core + TSA SV + SL/ST + CY's polygon, with CY's supplement amount differing). FWS, Title 38, NAF wage, and SES/EX postings sit on different geography or none." State Roundup and County Detail keep their compensation rows but gain a small "postings by pay-area kind" breakdown so the locality story doesn't pretend to cover the FWS / Title 38 / no-locality slice that physically lives inside the same polygon.

6. **Deferral schedule (rewritten).** Nothing in this ADR ships before V1 is callable done. The original V1.5 plan is withdrawn; reintroducing any of it requires the operator to settle the Open Questions below and explicitly schedule the work.
   - **Binds immediately, regardless of schedule:** the no-widen rule (item 4). No PR may grow `pay_scales` for non-`gs_table` plans. This is a code-review guard, not a sequenced feature.
   - **V2 candidate (needs further discussion):** the per-plan strategy field on `pay_plans`, the plan→strategy seed table, the calculator dispatch, the five non-GS JobCard renderers, the Admin "Unregistered pay plans" panel, and the locality-polygon label change to "GS locality pay area." Sequenced only after V1 ships and the operator confirms that the GS-only JobCard is causing visible misinformation worth fixing.
   - **V2+ candidate (needs further discussion):** the two-axis `pay_area_kind` field (item 7).
   - **V2+ candidate (needs further discussion):** the Locality-Pinned View (item 8).
   - **Out of scope until at least one of the above ships:** FWS wage-area layer, Title 38 facility panels, Foreign Service post differentials, special-rates "higher of" logic. These were previously sequenced as Phase 13 / 14 / V2+; that sequencing is withdrawn and will be re-decided once item 7's pay-area-kind model is approved.

7. **Two-axis pay-area-kind model (Proposed; not implemented).** A pay plan has two independent attributes that the rate-table architecture has been conflating:

   - **Table shape** (the existing `pay_resolution_strategy`): `gs_table`, `range_only`, `facility_panel`, `wage_area_table`, `single_rate`, `none`. Determines what the JobCard renders.
   - **Pay-area kind** (new field, `pay_area_kind`): `gs_locality`, `lms_replacement`, `fws_wage_area`, `facility_specific`, `bah_area`, `none`. Determines which geography the plan's pay actually varies on, independent of the rate-table shape.

   These axes are independent. AcqDemo (`NH`/`NJ`/`NK`) is `range_only` table shape with `gs_locality` pay-area kind — the broadband ranges differ by GS locality. SES (`ES`) is `range_only` with `none` — same range nationwide. FWS (`WG`/`WL`/`WS`) is `wage_area_table` with `fws_wage_area`. Title 38 nurses (`VN`) are `facility_panel` with `facility_specific`. DoD Cyber (`CY`) is `range_only` with `lms_replacement` — same 58 polygon geometry as GS locality, but the supplement amount comes from a published LMS table (and TLMS for STEM/cyber roles), not the OPM locality %.

   Implication: the locality polygon layer is the correct geography for any plan whose `pay_area_kind` is `gs_locality` *or* `lms_replacement` — empirically ~75% of postings, not the ~53% covered by `pay_resolution_strategy='gs_table'`. The "GS-family only" framing in earlier items of this ADR is too narrow at the geography layer; it remains correct at the rate-table layer. Items 1, 2, 4 above are unchanged because they describe the rate-table layer.

   Open question (see below): should `pay_area_kind` live as a column on `pay_plans`, or in a separate `pay_systems` table that `pay_plans.code` joins to? Geography evolves slower than rate tables.

8. **Locality-Pinned View tool (Proposed feature; needs further discussion).** A new public-map view that makes the locality polygon honest by showing what it actually does and doesn't affect. Activation: user clicks a GS locality polygon, or selects "View by locality" from a polygon's scoped action window (CLAUDE.md rule 16), or applies a locality chip from the Compensation Comparator. Effects:

   - The map filters to postings physically located inside that locality's constituent counties (using `locality_pay_counties`).
   - Marker color/style is driven by the posting's `pay_area_kind`:
     - `gs_locality` postings render as the primary marker color (matching the polygon's choropleth intensity) — these are the jobs whose pay the locality % actually affects.
     - `lms_replacement` postings (CY etc.) render as the primary color with a small overlay badge indicating "same polygon, different supplement (LMS)."
     - `fws_wage_area`, `facility_specific`, `bah_area`, `none` postings render in a desaturated style with a "different pay geography" badge — they're geographically in the locality but their pay does not vary by it.
   - A side panel summarizes counts by `pay_area_kind`, with the "different geography" group expandable to its sub-kinds (FWS / Title 38 facility / NAF wage / SES / EX / Commissioned Corps / AD).
   - An "Add to Search" chip applies a locality filter (per CLAUDE.md rule 17, additive with other geography chips).

   Purpose: demonstrate visually that the locality polygon is meaningful for most postings inside it but not all, so the user understands which jobs the choropleth color is "about." Replaces the implicit promise of the current polygon layer (which appears to color *all* postings) with an explicit one.

   Not designed yet. The decision items above (especially item 7's `pay_area_kind`) are prerequisites. Implementation, UI mockups, marker style choices, and panel layout are deferred to a future ADR or planning doc when the operator decides to schedule this.

9. **Active scope.** From this revision until further notice, the only thing in this ADR that's actually "on": the **no-widen rule in item 4 binds today** as a code-review guard. The taxonomy in items 1–3, the broadened choropleth scope in item 5, the two-axis model in item 7, and the Locality-Pinned View in item 8 are recorded as design direction for future work and are not on any current sprint.

**Open Questions** (must be settled before any work in this ADR is scheduled):
1. Given that the dashboard's JobCard is GS-only today, is the right next move to (a) build the per-plan renderers in this ADR, (b) ship the Locality-Pinned View tool, or (c) something else — and which user-visible problem is most worth solving first?
2. Does `pay_area_kind` belong on `pay_plans` (one row per plan code) or in a separate `pay_systems` table that plans reference? FWS sub-codes (`WG`/`WL`/`WS`) all share one wage-area geometry, suggesting separation; AcqDemo (`NH`/`NJ`/`NK`) all share one geometry too.
3. For `CY` and other LMS plans: does the choropleth show GS-13 step 1 *with GS locality %* (the current reference cell), or does the legend explicitly say "this color reflects GS locality math; CY postings inside this polygon use LMS, which differs"? The first is simpler; the second is more honest.
4. Is the Locality-Pinned View a V2 feature or a smaller V1.5 add-on that just adds a marker-coloring branch to the existing polygon click? The latter is cheap; the former is a bigger UI commitment.
5. For Title 38 (`VN`/`VM`): facility-level pay isn't a polygon at all — it's a point per VAMC. Does the Locality-Pinned View show these as the "different geography" desaturated markers (current proposal), or does it eventually grow a separate VA-facility overlay (similar to ADR-0025's FRPP layer) so the user can see the actual facility pay schedules?
6. Is the Phase 13 / Phase 14 sequencing (FWS, then Title 38) still right, or does the data argue for Title 38 first given VM is the 4th-largest plan in the live audit?

**Consequences (revised).** Recording this ADR has three effects today and zero implementation effects until the operator schedules work. (1) The no-widen rule in item 4 is a code-review guard that prevents the most likely regression — someone "just adding a few rows" to `pay_scales` for FWS or Title 38. (2) Future work on pay rendering, locality scoping, and the Locality-Pinned View shares a single taxonomy, so we don't end up with three slightly-different implementations. (3) The audit query (`SELECT pay_plan, COUNT(*) FROM jobs GROUP BY pay_plan`) becomes a recurring admin-page sanity check and a freshness signal for the Open Questions above — as USAJOBS coverage broadens, the distribution will shift and the prioritization may change. No code, schema, or UI changes from this ADR; rule 10 in CLAUDE.md is reframed in parallel to clarify that the per-plan rendering is target direction, not current behavior, while the no-widen guard binds today.

