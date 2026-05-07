# CLAUDE.md

Guidance for Claude Code (or any AI assistant) working in this repo.

## Source of truth

`Project_Start.md` is the definitive project brief. When in doubt, defer to it. Planning docs in `docs/` elaborate on it but never contradict it.

For USAJOBS API parameters, go to the official docs first: <https://developer.usajobs.gov/api-reference/>. The local SIF guide and Excel data dictionaries are field-semantics sources, not REST parameter sources. Use `docs/USAJOBS_DATA_STRUCTURES.md` as the local reconciliation map.

For schema expansion, use `docs/SCHEMA_EXPANSION_PLAN.md` as the implementation queue and guardrail. Do not create one table per SIF field; add a table only when the plan's design rule is met: repeated per job, code-list backed, UI-filterable/groupable, scoring/application evidence, or unsafe as one scalar on `jobs`.

## What this project is

A local-first Python/Streamlit/SQLite dashboard for USAJOBS posting data and OPM workforce data. The user is the sole user. The user is not a professional coder and runs everything locally.

## Current architecture state

- Phase 1 reconnaissance is implemented in `src/data_recon.py`.
- Phase 2 SQLite persistence is implemented in `src/database.py`.
- Phase 3 USAJOBS import work lives in `src/data_import.py` plus endpoint wrappers: `src/usajobs_current_api.py`, `src/usajobs_historic_api.py`, and `src/usajobs_announcement_text_api.py`.
- Phase 4 Streamlit UI is implemented in `app.py` and `pages/`.
- Phase 5 rule-based scoring is implemented in `src/scoring.py`; current rules are documented in `docs/SCORING_RULES.md`.
- Phase 6 local alerts are implemented in `src/alerts.py`; alerts are generated manually in the app, deduped in SQLite, visible in Data Admin and Saved Jobs, and exportable as CSV. Email/push alerts are out of scope for V1.
- Phase 6.5 preference feedback and explainable similar-job recommendations are implemented in `src/recommendations.py`, backed by `job_feedback`, `recommendation_runs`, and `job_recommendations`.
- Phase 7 OPM file ingestion and map source switching are implemented in `src/opm_data.py`, `pages/7_Data_Admin.py`, and `pages/4_State_Map.py`. OPM data is file-based and must stay labeled as workforce/accessions/separations, not postings.
- Phase 8 CSV/Excel exports are implemented in `src/exports.py` and exposed for saved jobs, scorecards, and alerts.
- V2 Application Tracker is implemented in `pages/6_Application_Tracker.py`, backed by `applications` and `application_events`. It is tracking-only and must never automate applications.
- V2 Resume Versions is implemented in `pages/9_Resume_Versions.py`, backed by `resume_versions`. It stores metadata only; do not parse or copy resume contents in V2.
- V2 Repost Detector is implemented in `pages/10_Repost_Detector.py`, backed by `repost_runs`, `repost_groups`, and `repost_group_members`. Treat groups as review evidence, not administrative certainty.
- Map behavior is specified in `docs/MAP_FEATURE_SPEC.md`; use that as the source of truth before changing `pages/4_State_Map.py`.
- The Public Map Tool (`thegrandpipeline.com/map`) is a separate sibling product per ADR-0016, ADR-0017, ADR-0018, ADR-0019. It lives in `public_map/` (SvelteKit + Mapbox GL JS, deployed to Cloudflare Pages) and is fed one-way by `scripts/export_public_map.py` writing static GeoJSON/JSON snapshots. The map is **layered and zoom-driven** (state choropleth â†’ locality / county / CBSA outlines â†’ marker clusters â†’ individual markers) with a hard **maxzoom of 9** (no street-level views). The dashboard's "no cloud / no FastAPI / no React" rule still applies to everything outside `public_map/`. The detailed implementation plan lives at `C:\Users\caleb\.claude\plans\review-the-new-map-playful-wind.md`.
- Public-map reference data lives in dedicated SQLite tables: `pay_plans`, `pay_scales`, `locality_pay_areas`, `locality_pay_counties`, `counties`, `metro_areas`, `state_polygons`, `cost_of_living_index`, `data_source_status`, `locations_geocoded`, `geocoding_misses`. Polygon GeoJSON is stored as files under `data/external/` and referenced by `polygon_path`. Pay calculation goes through `src/pay_calculator.py`; status read/write through `src/data_source_registry.py`; reads through `src/reference_data.py`. Per-source ingest scripts live in `scripts/ingest_*.py` and are orchestrated by `scripts/refresh_public_map_data.py`.
- A local-only Streamlit page `pages/11_Public_Map_Admin.py` is the operator console for public-map data: per-source status, last-success time, row counts, year-over-year diffs, manual refresh, and CSV upload override. This page is part of the dashboard and never deployed.
- Reference docs for the public map: `docs/PUBLIC_MAP_DATA_SOURCES.md` (catalog of every external dataset), `docs/PUBLIC_MAP_PIPELINE.md` (operator runbook), and the Public Map section of `docs/PRODUCT_SPEC.md` (vision and definition of done).
- Phase A.7: `src/public_map_export.py` also emits `states.geojson`, `localities.geojson`, `counties.geojson`, `metros.geojson`, `pay_tables.json`, and `cost_of_living.json`; each polygon feature joins postings, OPM workforce, BEA RPP, illustrative GS-13 pay, and pay-vs-COL; markers carry `locality_code`; `manifest.json` exposes per-source freshness, layer counts, and the resolved reference year; stdlib Douglas-Peucker simplification runs at export time.
- Phase B (skeleton): `public_map/` is a SvelteKit + Mapbox GL JS app (Svelte 5, Vite 6, `adapter-static`, SPA mode). Layer order is enforced in `public_map/src/lib/layers.ts`: basemap → states fill → counties outline → metros outline → localities fill+outline → marker clusters → individual markers. Map is capped at `maxZoom: 9`; markers and clusters use `minzoom: 7`. The choropleth metric switcher (`public_map/src/lib/MetricSwitcher.svelte`) covers postings / workforce / accessions / separations / remote share / pay-vs-COL; `remote_share` is derived client-side because the export does not pre-compute it. Without a `VITE_MAPBOX_TOKEN` the basemap falls back to OSM raster tiles so `npm run dev` works without sign-up. Phase B exposes only a debug click-through; popups and filters land in Phase C/D.
- USAJOBS field mapping lives in `src/usajobs_normalize.py`. Do not duplicate normalization logic inside UI pages or importers.
- Preference learning / recommendations must remain inspectable: user feedback accepts both a structured signal (`liked`, `disliked`, `more_like_this`, `less_like_this`) and a short free-text explanation for later review. Suggested jobs must always expose "why suggested" factors; do not add opaque recommendations.

## USAJOBS data layers

- `/api/Search` is the current live listings layer. It requires USAJOBS credentials and is capped by USAJOBS Search limits. Use this for "what can I apply to right now?" For agency targeting, use `Organization=<agency subelement code>`; FEMA is `Organization=HSCB`.
- `/api/historicjoa` is the structured archive layer. It is public bulk data with continuation-token paging. Use it for the local historical database, trend charts, maps, and scorecards. For agency targeting, use `HiringAgencyCodes`; FEMA is `HiringAgencyCodes=HSCB`.
- `/api/historicjoa/announcementtext` is the long-form selected text layer. Pull it selectively, not wholesale at startup. For agency/date slices, use the same filters as HistoricJoa instead of one request per control number.
- The two most important long-form fields for matching are `summary`, stored as `job_text.summary`, and `requirementsQualifications`, stored as `job_text.qualifications`.
- `summary` is the top description of what the job is. `requirementsQualifications` contains the GS-equivalency / specialized-experience language.
- Prefer filter-based UI/import scopes over keyword search. Keyword is useful for discovery, but agency code, department code, series, grade, date, location, and hiring-path filters should drive reproducible imports.
- Current `jobs` rows are flattened summaries. USAJOBS/SIF data contains repeated locations, series, hiring paths, and required documents; Phase 4.5 stores those in child tables before broad imports or serious scoring.
- Implemented schema-expansion tables include `job_import_scopes`, `job_grades`, `job_salary_ranges`, `job_requirements`, `job_qualification_requirements`, `job_duties`, `job_evaluation_factors`, `job_openings`, `job_contacts`, `job_security_clearances`, `job_travel_requirements`, and `job_application_options`. Media/cyber/vendor/SIF-transaction tables should wait until an actual product workflow needs them.

## Hard rules

1. **Never hardcode API keys.** Credentials live only in `.env` (read via `python-dotenv`). `.env` is gitignored; `.env.example` is the template.
2. **Postings â‰  hires.** Use "postings" or "announcements" for USAJOBS data and "hires", "accessions", "separations", or "workforce counts" for OPM data. Charts and maps must label the data source.
3. **No full download without reconnaissance.** Before downloading any large dataset, run `src/data_recon.py` and write the recommendation to `docs/DOWNLOAD_STRATEGY.md`. The user explicitly approves the mode (`FULL_DOWNLOAD` | `FOCUSED_FULL_DOWNLOAD` | `STAGED_DOWNLOAD` | `SAMPLE_ONLY`).
4. **Respect rate limits.** Implement paging, backoff, retry, and resumable imports. Save every raw response to `data/raw/...`. Track each request in `raw_api_responses` and each import run in `import_manifests`.
5. **Deduplicate.** Use position ID + announcement number + source as the dedup key for jobs. Upserts only â€” never blind insert.
6. **Transparent scoring in V1.** The match-score module is rule-based, returns a 0â€“100 score plus a list of positive factors, negative factors, and missing info. **Do not call an LLM for scoring in V1.**
7. **No advanced features in V1.** No React, FastAPI, Docker, cloud deployment, user accounts, vector DB, paid APIs, browser scraping, or auto-applications. See `docs/ROADMAP.md` for what belongs where. **Exception:** the `public_map/` subdirectory is a separate sibling product per ADR-0016 (a static, read-only SvelteKit site at `thegrandpipeline.com/map` fed by nightly snapshots). The dashboard itself stays local-first and unchanged.
8. **Tests live next to features.** Anything in `src/` has a matching `tests/test_*.py`. Use mocked HTTP responses; do not hit real USAJOBS endpoints in tests.
9. **Preserve control numbers.** Keep `usajobs_control_number` on imported jobs; it is the join key between HistoricJoa structured rows and selected AnnouncementText rows.

## Build order (strict)

1. Planning docs (this phase).
2. `src/data_recon.py` + `src/logging_utils.py` + tests.
3. `src/database.py` + tests.
4. USAJOBS importers (`src/usajobs_current_api.py`, `src/usajobs_historic_api.py`, `src/usajobs_announcement_text_api.py`, `src/data_import.py`) + tests.
5. Streamlit app + pages.
6. Phase 4.5 data structure hardening: agency/code tables, repeated-structure child tables, and filter-first import/UI scopes.
   - Follow `docs/SCHEMA_EXPANSION_PLAN.md` for table priority and "do not model everything" rules.
7. `src/scoring.py` + tests. **Done for V1 `v1.0`; update `docs/SCORING_RULES.md` when changing weights.**
8. `src/alerts.py` + tests. **Done for local/manual V1 alerts; no email yet.**
9. Recommendation feedback/similarity. **Done for deterministic local recommendations; embeddings remain V3.**
10. OPM importer and map source switch. **Done for file import and state-level workforce/accession/separation maps.**
11. Maps, scorecards, exports. **Done for CSV/Excel exports of saved jobs, scorecards, and alerts.**
12. V2 tracking/intelligence: Application Tracker, Resume Versions, and Repost Detector are implemented. Remaining V2 starts with closing-window analytics; RAG/vector matching remains V3.

Do not skip ahead.

## Coding conventions

- Python 3.11+. Type hints on all public functions.
- Module-level `logger = logging.getLogger(__name__)`. No `print()` in `src/`.
- Functions that hit the network take a `dry_run: bool = False` and a `max_pages: int | None = None` parameter for testability.
- Database access goes through `src/database.py`. Pages and importers do not write SQL directly.
- All times stored as ISO-8601 UTC strings. Convert at the edge.
- Filenames in `data/raw/` follow `{source}/{endpoint}/{YYYYMMDD}/{query_hash}_{page}.json`.
- Tests mock HTTP with `responses` or pytest `monkeypatch`; tests must not make real network calls.

## When the user asks to add something not in the roadmap

Push back. Ask whether it belongs in V1, V2, or V3 and update `docs/ROADMAP.md` and `docs/DECISIONS.md` before coding. Cleanup of the roadmap is preferable to surprise scope creep.

## Things to ask before coding, not after

- Is the dataset within the configured size thresholds?
- Does the importer have a resumable manifest entry?
- Are tests written first or alongside?
- Has the field been added to `docs/FIELD_DICTIONARY.md`?
- If adding a table, does `docs/SCHEMA_EXPANSION_PLAN.md` say it is necessary now?

## Useful references

- USAJOBS API: <https://developer.usajobs.gov/api-reference/>
- USAJOBS rate limits: <https://developer.usajobs.gov/guides/rate-limiting>
- OPM data: <https://data.opm.gov/>
- FedScope: <https://www.opm.gov/policy-data-oversight/data-analysis-documentation/fedscope/>
