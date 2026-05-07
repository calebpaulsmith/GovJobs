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

Every marker carries a `geo_quality` flag (`city` or `state_centroid`) which the UI surfaces. The flagship choropleth metric is **pay-vs-cost-of-living ratio** = locality-adjusted pay Ã· BEA Regional Price Parity, expressed as a number where 100 = national average. State, locality, county, and marker layers are all clickable with their own popups.

**Consequences.** The map is honest about precision. The state/locality/county roundup popups become a primary feature, not an afterthought. The choropleth metric switcher requires a robust reference-data layer (pay tables, COL, polygons) â€” see ADR-0018. The 9-zoom cap also has a side benefit: the polygon GeoJSON files don't need high-resolution geometry, keeping the public bundle small.

---

## ADR-0018 - Reference data is local-first and admin-managed, with per-source status tracking
Date: 2026-05-06
Status: Accepted

**Context.** The public map needs annual data from at least four federal sources (OPM pay tables across many pay plans, OPM locality definitions, Census TIGER polygons, BEA RPP) plus a third-party COL backup. The user has stated the bar is "exquisite" â€” pay data accuracy is non-negotiable â€” but is the sole operator and not a software engineer. Bad imports must be detectable, and manual override must be available when an automated source breaks or is wrong.

**Decision.** Every external dataset has a row in a new `data_source_status` table with a stable `source_key`, display name, category, last run / success / error timestamps, row count, manual-override flag, and notes. A new local-only Streamlit page (`pages/9_Public_Map_Admin.py`) renders this table and provides per-source actions: refresh now, upload override, view recent diff. Every ingest script writes its result back to `data_source_status`. The admin page is part of the dashboard's `pages/` tree and never appears on the public site.

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
