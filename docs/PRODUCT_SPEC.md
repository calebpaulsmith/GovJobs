# PRODUCT_SPEC.md

## Purpose

A local, single-user dashboard that turns USAJOBS posting data and OPM workforce data into actionable career intelligence — specifically tilted toward FEMA/DHS/emergency-management/grants/policy work at GS-13 through GS-15, with a Chicago/Midwest and remote bias.

## Non-goals (V1)

- No multi-user / no auth / no SaaS.
- No automated job applications.
- No browser scraping.
- No paid AI APIs.
- No vector search / RAG (V3 only).
- No mobile UI.

## Users and personas

Single user: a federal-careers-focused analyst who can run a Streamlit app, edit a `.env` file, and read a Plotly chart, but is not a software engineer. AI assistants (Claude Code, Codex) are co-users that read this spec to extend the codebase safely.

## Core terminology (must be honored everywhere)

| Term | Means | Source |
| --- | --- | --- |
| Posting / announcement | A USAJOBS Job Opportunity Announcement (JOA) | USAJOBS APIs |
| Hire / accession | A federal new hire recorded by OPM | OPM datasets |
| Separation | A federal employee leaving service | OPM datasets |
| Workforce count | Headcount on a reporting date | OPM datasets |

A posting is *not* a hire. Multiple postings can lead to one hire; one posting can fill many positions; some postings produce zero hires.

## Product principles

- Prefer structured filters over broad keyword searches. The app should guide the user toward agency codes, department codes, occupational series, grade/pay plan, location, remote status, dates, hiring paths, travel, security clearance, and supervisory status.
- Keep keyword search available, but treat it as a secondary text filter for discovery and narrowing.
- Preserve repeated structures from the source data. A job can have multiple locations, series, hiring paths, and required documents; the UI should not pretend those are always single values.
- The map should behave like a lightweight GIS review map, not only a dashboard chart. It should use detailed street/imagery base layers, support pan/zoom, and show actual work-location points where coordinates exist. Current Search locations can include latitude/longitude and should render as zoomable points. HistoricJoa commonly provides city/state/country without street address or coordinates, so historical rows do not need exact point placement. `docs/MAP_FEATURE_SPEC.md` is the detailed reusable feature sheet for map behavior.
- Preference learning must be explainable. When the user marks a job as liked/disliked or "more/less like this," the app should accept a short explanation for later review, and every suggested job must offer a "why suggested" view.

## V1 user stories

1. *As a user,* I open the app and see whether the database is initialized and how fresh the data is, so I know what I'm looking at.
2. *As a user,* I run a current USAJOBS search with structured filters (agency code/name, series, grade, salary, location, remote, date) plus optional keyword text, and view results in a sortable table with a link back to USAJOBS.
3. *As a user,* I save a job, tag it, add a note, and assign a status (New, Interested, Maybe, Applied, Referred, Interview, Selected, Not selected, Skip, Archived).
4. *As a user,* I see a transparent match score 0–100 for each job along with positive factors, negative factors, and missing info.
5. *As a user,* I import historical USAJOBS data by filter scope (agency code, department code, series, date range, grade/pay plan), but only after the recon step recommends a download mode and I approve it.
6. *As a user,* I view trend charts: postings over time, by agency, by series, by grade, by state; remote share over time; salary range over time.
7. *As a user,* I view a GIS-style map of current postings by actual work-location points when coordinates are present. Multi-location postings may appear in more than one place, but I can filter them out. Remote-anywhere postings are kept in a table and never plotted as a fake state/location. Current non-remote postings without mappable coordinates are not excluded; when I zoom into an area, they appear in an unmapped-current-postings table for that visible area.
8. *As a user,* I view scorecards (hottest agencies/series/locations/grades; best remote opportunities; best matches).
9. *As a user,* I see a list of local alerts (saved-search matches, high score, closing soon, reposted) and can export them to CSV.
10. *As a user,* I open the Data Admin page to see import status, last API pull, errors, raw-folder size, and database size.
11. *As a user,* I can mark jobs as liked, disliked, more like this, or less like this, optionally with a short explanation, so the app can learn my preferences without losing my reasoning.
12. *As a user,* I can review suggested similar jobs and open an explanation showing exactly which shared fields, text signals, or feedback patterns caused the suggestion.

## V2 user stories (after V1 is stable)

11. Track applications end-to-end with résumé version, submission date, USAJOBS reference, outcome, next action, and event history. **Implemented as a local/manual tracker.**
12. Manage resume version labels, filenames, local paths, target series/grade, active/archive status, and notes without parsing resume contents. **Implemented as a local/manual library.**
13. Detect reposts of the same announcement by similarity of title/series/agency/text hash. **Implemented as a deterministic local detector with persisted groups and alert integration.**
14. Closing-window tracker (median days open by series and grade).
15. Compare USAJOBS posting volume to OPM accession volume by agency/series.
16. Locality-adjusted salary view.
17. Improved hotness model.
18. Excel/PDF export of saved jobs and scorecards.
19. Personal agency / series notes (separate from per-job notes).
20. Career-ladder categorization (e.g., "GS-12 -> GS-13 ladder").
21. Improved preference learning using saved feedback history, negative preferences, and explanation review.

## V3 user stories (AI / RAG)

22. Vector search across job duties, qualifications, specialized experience, and resume text.
23. Resume-to-announcement matching that returns score, evidence, missing keywords, and "should I apply?" recommendation. **Must not invent experience.**
24. Hidden-opportunity finder for jobs whose titles do not use obvious keywords.
25. Application-strategy generator (key announcement language, resume sections to emphasize, weaknesses, pre-application questions).

## Definition of done — V1

The build is done when:

1. `streamlit run app.py` opens the app locally.
2. SQLite DB initializes from a clean checkout.
3. Current USAJOBS search works.
4. Historic JOA import works for at least a limited date range.
5. Recon step produces a `DOWNLOAD_STRATEGY.md` recommendation.
6. Raw API responses are saved on disk; jobs are deduplicated.
7. Filters work in the UI.
8. Save / tag / note / status all work.
9. Match scoring (rule-based) works and is shown on every job.
10. Trend charts, state map, and scorecards render when data is present.
11. Admin page shows import status and freshness.
12. Tests pass with `pytest`.
13. README explains setup and run.

## Out-of-scope clarifications (dashboard)

- We will not build email/push notifications in V1; local in-app alerts are manual and stored in SQLite.
- We will not call any LLM in V1 — scoring is rule-based.
- We will not deploy the **dashboard** to the cloud. The dashboard is local-first.

The Public Map Tool below is a **separate sibling product** (ADR-0016) that is hosted, not a deployment of the dashboard.

---

## Public Map Tool — `thegrandpipeline.com/map`

A separate, public-facing, static web tool that helps anyone find federal jobs on a map. Fed one-way by nightly snapshots from the local dashboard's SQLite. The dashboard remains local-first; the public map is the only piece that ever lives on the internet.

### Name and guiding principles

The public map is branded **FedFinder** — the masthead wordmark and the product's public name. It is a public, read-only web map of live federal job postings with one job: help someone decide *where to apply for federal work*, by placing USAJOBS postings on a map alongside pay, cost-of-living, and hiring-climate context. No accounts, no applications, no scraping — FedFinder only reflects USAJOBS and OPM/BEA reference data.

Three principles govern every screen and every UI element:

1. **Every screen has one verb.** Browse = *decide* what to apply to now. Map-only = *explore* where federal hiring is happening. Localities = *compare* places against each other. If a screen needs two verbs to describe it, it is two screens.
2. **Every element earns its place by naming the activity it serves.** Before adding a control, state which verb it enables; if you cannot, cut it. This is why the Browse rev-2 design folded the standalone metric switcher into the area card — it was an *option*, not an *activity*.
3. **Default to fewer choices; reflect, don't editorialize.** Rare or advanced options hide behind a single disclosure ("More filters"). Numbers are source-labeled, area prose is deterministic templated text — never an LLM call — and subjective composite scores are forbidden.

### Vision

A federal job-search map that is honest about precision and surfaces the question every applicant actually asks: **"Where will my paycheck go furthest?"** The map answers that question by combining USAJOBS posting data, OPM federal workforce data, OPM locality pay tables, and BEA Regional Price Parities into a single zoomable surface.

### Interaction model

- **National / state zoom (3–5)**: choropleth of states. Metric is user-selectable: open postings, federal workforce density, accessions, separations, remote-eligible postings, and the flagship **pay-vs-cost-of-living ratio**. Click a state for a roundup popup.
- **Regional zoom (5–7)**: locality pay area outlines fade in over the state choropleth. Click a locality for its pay adjustment, member counties, sample pay tables, and COL.
- **Metro / county zoom (7–9)**: county and CBSA outlines plus emerging marker clusters. Click a county or metro for COL and stats.
- **Maxzoom 9 (cap)**: individual job markers placed by coordinate priority — `source` (authoritative USAJOBS Search lat/lon stored in `job_locations`), then `city` (SimpleMaps centroid), then `state_centroid` (last-resort). The `geo_quality` flag is surfaced in the UI so users can see how precise each marker is. The map never goes to street level — even when source coords exist, the maxzoom cap keeps the public surface uniform.

The click model is snap-scoped: clicking a state or locality fits the map to that polygon and opens a compact action window. The future city polygon layer uses the same contract. The window can search only that geography, optionally include remote jobs, add the geography to the current search, and preview counts with global filters applied or temporarily ignored. Geography chips are additive: multiple geographic scopes are ORed with each other and ANDed with the rest of the user's filters.

### Pay-table fidelity

Pay data must be **exquisite**. Every USAJOBS pay plan we encounter (GS first, then Federal Wage System, ES, AD, FP, LE, VN, others incrementally) is supported with:

- Annual pay scales sourced from OPM, stored per pay plan / year / grade / step / locality
- Official 2026 GS base and locality pay tables as the public-map V1 reference year; older checked-in seeds are development fallbacks only
- Locality-adjusted rates derived for every job from its (city, state) → county → locality chain
- A full pay table (every step) shown in the marker detail card
- Year-over-year diffs visible in the admin dashboard so import errors are caught before they reach the public site

### Polygon layers

- **States** (Census TIGER) — 56 features (50 states + DC + territories)
- **Locality pay areas** (OPM) — ~58 features. Polygons sourced from the public OPM ArcGIS FeatureServer; membership cross-validated against OPM's annual county-FIPS definition list (5 CFR 531.603); fallback rebuild path is dissolving Census counties by membership list.
- **Counties** (Census TIGER) — ~3,200 features
- **CBSAs / metro areas** (Census TIGER) — ~390 features

All clickable; all sourced from public, federally-published datasets.

### Cost of living

V1 uses BEA Regional Price Parities (free, official, state and metro level). Locality-area COL is derived by averaging across constituent metros and labeled as approximate. C2ER is reserved as a paid upgrade path (~$200/yr) if richer granularity is needed.

The map also includes a personal compensation comparator. A visitor can enter a GS grade/step plus locality, or a custom annual wage, and optionally a current comparison city. The output expresses purchasing-power equivalents such as "GS-13 Step 2 in Denver is equivalent to making $X in Chicago." Every comparison labels the source vintage and whether the city/locality COL value is exact, derived, or a fallback.

### Public-map user stories (V1)

1. *As a visitor,* I see a heat surface of open USAJOBS postings at every zoom from national down to metro so I can scan where activity is concentrated even before I drill in.
2. *As a visitor,* I type "FEMA" in the agency field and the typeahead surfaces `HSCB — Federal Emergency Management Agency · DHS`; pressing Enter commits a chip. I add `NTSB`; the map narrows to both. The chips can be removed individually and the URL captures every code so I can share the view.
3. *As a visitor,* I save my current filter set under a name like "FEMA + DC + GS-13 remote." When I return tomorrow the saved view restores my filters, the active metric, the address-zoom target, and the map center+zoom.
4. *As a visitor,* I paste a ZIP code or street address into the address bar and the map flies to that location with a transient flag pin so I can see what's open near me. The pin is never confused with a job marker.
5. *As a visitor,* I click a state at low zoom and the map both opens the state roundup *and* fits its bounds so I can immediately see the state in detail. The same gesture works for localities, counties, and CBSAs at their zoom bands. A "back to national" affordance returns me home.
6. *As a visitor,* I see only choropleth metrics that actually have data — every metric is labeled `ready`, `wip`, or `under construction`, and partial data is never colored as if it were complete.
7. *As a visitor,* I can toggle a "Federal properties" layer to see GSA-owned buildings as small neutral diamonds; agency chip filters apply to both job markers and properties, so I can see "FEMA postings near FEMA buildings" at a glance.
8. *As a visitor,* I can toggle a "Recently closed (90 days)" layer to see what's just closed in my region, distinct from open markers, for context on hiring tempo.
9. *As a visitor,* every job marker reveals a full locality-adjusted pay grid (grade × step) on click, with a citation to the OPM source year. When the underlying pay scale is missing, the card says so plainly and points to the admin page.
10. *As a visitor,* county and locality popups show cost-of-living to the most precise level available — county-level when ingested, state-level fallback labeled "approximate" otherwise.

11. *As a visitor,* I click Illinois or the Chicago locality and the map snaps there, opens a small window for that geography, and lets me search only that area, include remote jobs, add the area to my current search, or temporarily ignore my global filters while previewing.
12. *As a visitor,* I can switch between light and dark mode; the map, panels, controls, and overlays remain legible and remember my choice.
13. *As a visitor,* I enter my expected grade/step and locality, or a custom wage, and compare it to my current city so I can see the cost-of-living equivalent before I relocate.
14. *As a visitor,* job cards warn me when a posting is closing soon or when a known applicant/opening signal suggests the job is filling up, without pretending counts exist when USAJOBS does not provide them.
15. *As a visitor,* jobs I have opened show a "viewed" marker across the map and lists, so I do not keep rereading the same announcement.
16. *As a visitor,* I can Save Job from a card or list row and later return to my saved jobs from a local profile area.
17. *As a visitor,* I can Hide Job from a card or list row, removing it from map markers, heat/list counts, and scoped search results by default, while still being able to restore it from Hidden Jobs in my local profile.
18. *As a visitor,* I can open a profile area that contains Saved Jobs, Hidden Jobs, and jobs I viewed that have since closed.

### Out of scope (public map V1)

- Server-side user accounts, cloud sync, scoring, recommendations, alerts. Local browser profile state for viewed/saved/hidden jobs is in scope for V1.
- Application submission. The public map only links out to canonical USAJOBS URLs; we never host applications.
- Live API. The public map is a static snapshot. No backend, no auth, no DB online.
- Street-level zoom.
- Anything that is not in service of "find a federal job on a map and understand the pay there."

### Definition of done — public map V1

1. Layered Mapbox GL map (or MapLibre, per ADR-0026 if invoked) renders at zoom 3–9 with state, locality, county, and metro polygons plus job markers and a persistent posting heat layer.
2. Choropleth metric switcher offers at least: postings, workforce, accessions, separations, pay-vs-COL — each with a `ready` / `wip` / `under construction` status; only `ready` metrics paint the map.
3. State / locality / county / marker / federal-property / closed-job popups all render with correct, sourced data; clicking any polygon also fits its bounds.
4. Marker detail panel shows a full locality-adjusted pay grid (grade × step) for every supported pay plan, with an `exact` / `approximated` / `unavailable` chip and an OPM source citation.
5. Agency filter is a code-backed multi-select (typeahead + chips); URL state and saved searches both round-trip through `agency=CODE` repeated keys.
6. Address / ZIP geocoder flies the map to a transient pin without creating a fake job marker.
7. Federal Real Property layer renders ≥ 1,000 georeferenced GSA buildings nationwide with agency-aware filtering.
8. County-level COL covers ≥ 50% of counties with markers; locality and county popups label precision honestly.
9. OSM fallback boots cleanly without a Mapbox token; the layer stack matches the Mapbox path.
10. Admin dashboard (local, private) lists every external data source with status, last-success time, row count, manual override, per-source refresh button, and metric-readiness summary.
11. UI layout: zero overlapping panels at 1440 × 900, 1024 × 768, and 720 × 1280; layout slots imported from `public_map/src/lib/layout.ts`.
12. Local corpus ≥ 5,000 open postings; trailing-90-days closed-postings overlay imports successfully.
13. Official 2026 GS base and locality tables are ingested; `manifest.json.reference_year` is 2026; sampled GS rows match OPM-published values exactly.
14. State and locality scoped windows support snap/focus, scoped search, remote inclusion, Add to Search, and a with/without-global-filters preview; the city layer has the same contract documented for its later implementation.
15. Light and dark modes are toggleable, persisted, and visually verified.
16. Compensation comparator returns sourced COL-adjusted equivalents for GS grade/step/locality and custom-wage inputs.
17. Job cards show closing-soon and source-backed fill/applicant badges when data exists.
18. Viewed/saved/hidden state persists locally; hidden jobs are excluded from default map/list/search views and recoverable from Hidden Jobs; viewed jobs that later close appear in the local profile.
19. Nightly export + git push + Cloudflare Pages rebuild lands on `thegrandpipeline.com/map`; footer credits every source with freshness.
20. `pytest` green; pay tables for at least three localities x three pay plans match published OPM values exactly; layout / typeahead / basemap-fallback / pay-grid / federal-properties / scoped-search / compensation-comparison / local-profile-state tests all green.

The full implementation plan lives in `docs/ROADMAP.md` (Public Map Tool track) and the detailed Phase D.5 sub-phase list in `C:\Users\caleb\.claude\plans\review-the-new-map-playful-wind.md`. External datasets are catalogued in `docs/PUBLIC_MAP_DATA_SOURCES.md`. Pipeline operations are documented in `docs/PUBLIC_MAP_PIPELINE.md`.
