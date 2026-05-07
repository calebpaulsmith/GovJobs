# PUBLIC_MAP_DATA_SOURCES.md

The complete catalog of every external dataset the Public Map Tool depends on. Each entry lists the source, the local table(s) it lands in, the ingest script, refresh cadence, and verification notes. Live status (last successful refresh, row counts, errors, manual override) is in the local admin dashboard at `pages/11_Public_Map_Admin.py`.

Per ADR-0018, every dataset is local-first and admin-managed. Per ADR-0019, locality polygons have a primary source and a fallback path.

## Convention

Every dataset has a stable `source_key` used in the `data_source_status` table and in admin UI. Keys are namespaced (`opm_*`, `census_*`, `bea_*`, `simplemaps_*`, `c2er_*`).

Refresh cadences:
- **Annual** (Jan/Feb): OPM pay tables, OPM locality definitions, OPM locality polygons, BEA RPP (lags one year)
- **Decennial / occasional**: Census state, county, CBSA polygons (boundaries change rarely)
- **Continuous**: USAJOBS postings (driven by the dashboard's existing import pipeline, not this catalog)
- **One-time**: SimpleMaps city geocoding (refresh only if the dataset is updated)

## Job postings

### `usajobs_search`

- **Source**: USAJOBS Search API. Already wired through the dashboard's existing importers — see `src/usajobs_current_api.py` and `src/data_import.py`.
- **Lands in**: `jobs`, `job_locations`, `job_categories`, `job_text`, etc.
- **Refresh**: triggered manually or on schedule from the dashboard (Data Admin page).
- **Public-map relevance**: provides every marker. The export filters to `close_date >= today`.
- **No new ingest script** — the dashboard owns this.

### `usajobs_historicjoa`

- **Source**: USAJOBS Historic JOA API. Already wired (`src/usajobs_historic_api.py`).
- **Public-map relevance**: optional — gives the public map historical context if exposed (out of scope for V1 public map).

## Geometry — boundary polygons

### `census_states`

- **Source**: Census Bureau TIGER/Line Shapefiles (cartographic boundary, 1:5,000,000 simplification). State boundaries.
  - URL: <https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_5m.zip>
  - License: U.S. public domain
- **Lands in**: `state_polygons` (path) + simplified GeoJSON file under `data/external/state_polygons/`
- **Ingest**: `scripts/ingest_state_polygons.py` (downloads, simplifies to ~10% with `topojson` or `shapely`, writes GeoJSON)
- **Refresh**: rare — when Census publishes new vintage
- **Verification**: 56 features (50 states + DC + 5 territories), each with `STUSPS` (e.g., `IL`) attribute

### `census_counties`

- **Source**: Census TIGER/Line CB shapefile, 1:500,000.
  - URL: <https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip>
  - License: public domain
- **Lands in**: `counties` (one row per county, polygon path) + GeoJSON file under `data/external/county_polygons/`
- **Ingest**: `scripts/ingest_county_polygons.py`
- **Refresh**: rare
- **Verification**: ~3,200 features, each with 5-digit `GEOID` (state FIPS + county FIPS)

### `census_cbsa`

- **Source**: Census TIGER/Line CB shapefile, Core Based Statistical Areas (Metro + Micro).
  - URL: <https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_cbsa_500k.zip>
- **Lands in**: `metro_areas` + GeoJSON under `data/external/metro_polygons/`
- **Ingest**: `scripts/ingest_cbsa_polygons.py`
- **Refresh**: rare
- **Verification**: ~390 metro CBSAs + ~540 micro CBSAs

## OPM — locality pay

### `opm_locality_definitions`

- **Source**: OPM annual locality pay area definitions. Canonical legal definition per 5 CFR 531.603. Published as a web page with a table of counties per locality area.
  - URL pattern: `https://www.opm.gov/policy-data-oversight/pay-leave/salaries-wages/{YEAR}/locality-pay-area-definitions/`
- **Lands in**: `locality_pay_counties` (locality_code, year, county_fips), `locality_pay_areas` (code, year, name, description)
- **Ingest**: `scripts/ingest_locality_definitions.py` (parses the OPM web page; supports manual CSV override per ADR-0018)
- **Refresh**: annual (Jan)
- **Verification**: ~58 localities × ~1–500 counties each. Spot-check that "CHI" includes Cook County (FIPS 17031).

### `opm_locality_pay`

- **Source**: OPM annual locality pay percentages.
  - URL pattern: `https://www.opm.gov/policy-data-oversight/pay-leave/salaries-wages/{YEAR}/general-schedule/`
- **Lands in**: `locality_pay_areas.adjustment_pct`
- **Ingest**: `scripts/ingest_locality_pay.py`
- **Refresh**: annual (Jan)
- **Verification**: 2026 Chicago should be ≈32–34% (locality % updates annually).

### `opm_locality_polygons`

- **Source (primary)**: OPM ArcGIS Online FeatureServer.
  - URL: `https://services1.arcgis.com/cc7nIINtrZ67dyVJ/arcgis/rest/services/Locality_Pay_Areas/FeatureServer/1`
  - Owner: `JasonKlyvert_NGA` (third-party publisher; cross-validated against `opm_locality_definitions`)
  - Format: ArcGIS JSON (we convert to GeoJSON)
  - Public, no key needed.
- **Source (fallback)**: dissolve `census_counties` polygons by `locality_pay_counties` membership for the year. Always available as long as those two are present.
- **Lands in**: `locality_pay_areas.polygon_path` + GeoJSON file under `data/external/locality_polygons/{year}/`
- **Ingest**: `scripts/ingest_locality_polygons.py` (tries ArcGIS first; on any failure, dissolves counties)
- **Refresh**: annual (Jan), or whenever county membership changes
- **Verification**: 58 polygon features in the OPM ArcGIS layer; dissolve path produces matching union geometry within tolerance

## OPM — pay scales

Pay data must be **exquisite**. Every row stores `source` and `source_url`. The admin dashboard's diff view shows year-over-year changes per (pay_plan, locality, grade, step).

### `opm_gs_base`

- **Source**: OPM General Schedule base pay table (no locality).
  - URL pattern: `https://www.opm.gov/policy-data-oversight/pay-leave/salaries-wages/salary-tables/{YEAR}/general-schedule/`
  - Format: HTML table; can also pull annual XML/PDFs.
- **Lands in**: `pay_scales` rows where `pay_plan='GS'`, `locality_code IS NULL`, all 15 grades × 10 steps.
- **Ingest**: `scripts/ingest_gs_pay.py --table=base`
- **Refresh**: annual (Jan)
- **Verification**: 150 rows per year; GS-13 step 1 (2026) should match the published value to the cent.

### `opm_gs_locality`

- **Source**: OPM GS locality pay tables, one per locality.
  - URL pattern: `https://www.opm.gov/policy-data-oversight/pay-leave/salaries-wages/salary-tables/{YEAR}/general-schedule/{LOCALITY}/`
- **Lands in**: `pay_scales` where `pay_plan='GS'`, `locality_code` set.
- **Ingest**: `scripts/ingest_gs_pay.py --table=locality` (iterates over every locality from `opm_locality_definitions`)
- **Refresh**: annual
- **Verification**: 58 localities × 150 rows ≈ 8,700 rows per year. Test set: GS-13 step 5 in CHI, DC, REST OF U.S. matched to OPM-published values.

### `opm_other_pay_plans`

Pay plans beyond GS. Started in V1 with the largest-by-headcount plans, then incremental.

| `pay_plan` | Description | Has locality? | Has steps? | Initial priority |
| --- | --- | --- | --- | --- |
| `GS` | General Schedule | yes | yes (1–10) | V1 — done |
| `FW` | Federal Wage System (blue-collar) | wage-area based | yes | V1 — first add |
| `ES` | Senior Executive Service | yes | no (single rate) | V1 |
| `AD` | Administratively Determined | varies | varies | incremental |
| `FP` | TSA pay bands | yes | bands | incremental |
| `LE` | Law Enforcement (special pay) | yes | yes | incremental |
| `VN` | Veterans Affairs Nurses | yes | yes | incremental |
| `EX` | Executive Schedule (Levels I–V) | no | no | low priority |
| `SL/ST` | Senior Level / Scientific & Professional | yes | no | low priority |

- **Source**: OPM publishes one page per pay plan; we ingest selectively. URLs vary; ingest script captures them per plan.
- **Lands in**: `pay_scales` with the appropriate `pay_plan`. `pay_plans` table records the plan's locality and step semantics.
- **Ingest**: `scripts/ingest_other_pay_plans.py --plan=FW` etc.
- **Refresh**: annual
- **Verification**: per-plan smoke tests against published OPM values; admin dashboard shows which plans are present, missing, or stale.

## Cost of living

### `bea_rpp`

- **Source**: U.S. Bureau of Economic Analysis Regional Price Parities. Free, official, downloadable.
  - URL: <https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area>
  - Format: CSV.
- **Lands in**: `cost_of_living_index` rows with `geo_type='state'` (51 rows) and `geo_type='cbsa'` (~390 rows). Stores `rpp_overall`, `rpp_goods`, `rpp_services`, `rpp_rents`.
- **Ingest**: `scripts/ingest_bea_rpp.py`
- **Refresh**: annual (typically Q4 of year+1; e.g., 2024 RPP releases in late 2025)
- **Verification**: state RPP for CA/NY/HI > 100; for MS/AR/WV < 100. Latest year present.
- **Limitations**: BEA does not publish locality-pay-area-level RPP. We average across constituent metros for the locality popup; the popup labels this as approximate. C2ER reserved as a paid backup with finer granularity.

### `c2er_cost_index` (paid backup, not active)

- **Source**: Council for Community and Economic Research, Cost of Living Index. ~$200/yr.
- **Lands in**: same `cost_of_living_index` table, with `source='c2er:cost_index'`.
- **Activate when**: BEA approximations prove insufficient or the user wants metropolitan/locality-level granularity.

## Geocoding

### `simplemaps_uscities`

- **Source**: SimpleMaps US Cities Basic, CC-BY 4.0.
  - URL: <https://simplemaps.com/data/us-cities>
- **Lands in**: `locations_geocoded` (city, state, lat, lon, county_fips) for ~30K cities + the 56 state centroids seeded in `init_schema`.
- **Ingest**: `scripts/geocode_locations.py --csv data/external/uscities.csv` (already shipped in Phase A)
- **Refresh**: occasional (when SimpleMaps publishes a new vintage)
- **Verification**: ~30K rows; major cities present (Chicago, DC, NYC, LA).
- **Attribution**: required in public footer ("City data © SimpleMaps, CC-BY 4.0").

## Basemap

### `mapbox_basemap`

- **Source**: Mapbox vector tiles (Streets v12 or a custom dark style). Token-gated.
- **License**: per Mapbox terms; free tier 50K loads/month.
- **Lands in**: not stored locally; tiles fetched at runtime by Mapbox GL JS.
- **Token security**: env var on Cloudflare Pages, restricted by URL referrer to `thegrandpipeline.com` and `*.pages.dev` (per ADR-0016).
- **Attribution**: "© Mapbox © OpenStreetMap" surfaced in the map UI per Mapbox terms.

## Reference: how to add a new data source

1. Pick a stable `source_key` matching the existing namespace (e.g., `opm_xyz_2026`).
2. Add the dataset to this file with all sections above.
3. Write `scripts/ingest_<source_key>.py` — must be idempotent and call into `src.data_source_registry` to record start/success/error.
4. If it has its own table or column, update `src/database.py` and bump `schema_version`.
5. Add it to `scripts/refresh_public_map_data.py` so the orchestrator includes it.
6. Surface it in `pages/11_Public_Map_Admin.py` (the page reads `data_source_status` so it picks up new keys automatically).
7. Reference the new fields in `src/public_map_export.py` if the public map should display them.
