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
- **Default seed (per ADR-0027)**: `data/external/opm_locality_definitions/2025.csv` (curated, checked in). Contains ~426 locality-county rows for ~38 of the most populated localities. Refresh by replacing this file with the full annual OPM CSV when published.

### `opm_locality_pay`

- **Source**: OPM annual locality pay percentages.
  - URL pattern: `https://www.opm.gov/policy-data-oversight/pay-leave/salaries-wages/{YEAR}/general-schedule/`
- **Lands in**: `locality_pay_areas.adjustment_pct`
- **Ingest**: `scripts/ingest_locality_pay.py`
- **Refresh**: annual (Jan)
- **Verification**: 2026 Chicago should be ≈32–34% (locality % updates annually).
- **Default seed (per ADR-0027)**: `data/external/opm_locality_pay/2025.csv` (curated, checked in). 60 rows covering the published 2025 EO percentages for ~58 localities + RUS.

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
- **Default seed (per ADR-0027)**: `data/external/opm_gs_pay/2025_base.csv` (curated, checked in). All 150 (15 grade x 10 step) cells of the 2025 GS base table. This is bootstrap/dev data only. Public-map V1 requires an official 2026 GS base seed/source and must export `reference_year: 2026`. Replace annually with the official OPM-published table.

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
- **Default seed (per ADR-0027)**: `data/external/bea_rpp/2023.csv` (curated, checked in). 51 rows covering all 50 states + DC for the 2023 RPP vintage (most recent published as of 2026-05). Replace when BEA releases a newer vintage.

### `c2er_cost_index` (paid backup, not active)

- **Source**: Council for Community and Economic Research, Cost of Living Index. ~$200/yr.
- **Lands in**: same `cost_of_living_index` table, with `source='c2er:cost_index'`.
- **Activate when**: BEA approximations prove insufficient or the user wants metropolitan/locality-level granularity.

## Federal real property

### `gsa_frpp`

- **Source**: GSA Federal Real Property Profile (FRPP) public open-data CSV. Snapshot of federally-owned and federally-leased buildings, structures, and land reported under 41 CFR 102-84.
  - Landing page: <https://www.gsa.gov/policy-regulations/policy/real-property-policy/asset-management/federal-real-property-profile-management-system/federal-real-property-public-data-set>
  - License: U.S. public domain
  - Format: CSV
  - Size: ≈ 250 MB raw; ≈ 110 K active georeferenced rows after filtering
- **Lands in**: `federal_properties` (one row per reported asset). Indexed by `state`, `county_fips`, `reporting_agency_code`.
- **Ingest**: `scripts/ingest_federal_properties.py` — streams the CSV, drops disposed and non-georeferenced rows, joins each to `counties` via `zip_centroids` for county FIPS, writes status to `data_source_status` under `gsa_frpp`.
- **Refresh**: annual (FRPP is published once per fiscal year)
- **Verification**: spot-check that DC has hundreds of properties, that FEMA-reported (`HSCB`) properties exist, that `square_footage` rolls up to within ±5% of the FRPP-published agency totals.
- **Public-map relevance**: drives `federal_properties.geojson`; agency chip filters apply to both jobs and properties so users can see hiring near existing federal infrastructure.
- **Fallback**: USA.gov "Where the Federal Government Has Buildings" if FRPP's CSV is paywalled or moved (record the swap and source URL in the `data_source_status` `notes` column).

## Geocoding

### `simplemaps_uscities`

- **Source**: SimpleMaps US Cities Basic, CC-BY 4.0.
  - URL: <https://simplemaps.com/data/us-cities>
- **Lands in**: `locations_geocoded` (city, state, lat, lon, county_fips) for ~30K cities + the 56 state centroids seeded in `init_schema`.
- **Ingest**: `scripts/geocode_locations.py --csv data/external/uscities.csv` (already shipped in Phase A)
- **Refresh**: occasional (when SimpleMaps publishes a new vintage)
- **Verification**: ~30K rows; major cities present (Chicago, DC, NYC, LA).
- **Attribution**: required in public footer ("City data © SimpleMaps, CC-BY 4.0").

### `census_zcta_gazetteer`

- **Source**: U.S. Census Bureau 2024 ZIP Code Tabulation Area Gazetteer.
  - URL: <https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip>
- **Lands in**: `zip_centroids` (zip, lat, lon, city, state, county_fips). New table introduced in D.5.4.
- **Ingest**: `scripts/ingest_zip_centroids.py`. Idempotent; writes status under `census_zcta_gazetteer`. Operator CSV overrides can use SimpleMaps-style columns (`zip`, `lat`, `lng`, `city`, `state_id`, `county_fips`) when city/state/county labels are desired.
- **Refresh**: occasional.
- **Public-map relevance**: powers the address / ZIP geocoder's offline path (no network required for ZIP queries) and gives FRPP rows a county FIPS when only a ZIP is reported.
- **Verification**: ~33K ZCTAs; spot-check `60601` (Chicago Loop), `20002` (NE DC), `99701` (Fairbanks).
- **Attribution**: U.S. Census Bureau. If a SimpleMaps override is used, add "ZIP data © SimpleMaps, CC-BY 4.0" to the public footer.

### `mapbox_geocoding`

- **Source**: Mapbox Geocoding API v5, `mapbox.places` endpoint. Token-gated (same token as `mapbox_basemap`).
  - URL: `https://api.mapbox.com/geocoding/v5/mapbox.places/{q}.json`
- **Lands in**: not stored — called at request time by the public map's address bar.
- **Token security**: same token, same URL referrer restrictions.
- **Public-map relevance**: primary geocoder for the address-zoom feature.
- **Fallback**: when the token is unset, the address bar uses Nominatim (`https://nominatim.openstreetmap.org/search`) with a `User-Agent` header per OSM usage policy. ZIPs always resolve from the static `zip_centroids.json` first.

### `agency_aliases`

- **Source**: curated CSV `data/external/agency_aliases.csv` (checked into the repo; small, plain text). Maps shorthand and acronyms to canonical USAJOBS sub-element codes. Examples: `FEMA → HSCB`, `ICE → HSBA`, `IRS → TR93`, `NASA → NN`.
- **Lands in**: `code_lists` rows under `list_name='agency_aliases'`. Loaded at schema init and refreshed by the alias ingest script.
- **Ingest**: `scripts/ingest_agency_aliases.py`. Idempotent; writes status under `agency_aliases`.
- **Refresh**: as needed when USAJOBS reorganizes agencies.
- **Public-map relevance**: feeds the typeahead's alias resolution so users do not need to know the cryptic sub-element code to find an agency.

## Cost-of-living augmentation (D.5.10)

### `census_acs_rent`

- **Source**: U.S. Census Bureau, ACS 5-year estimates, table B25064 (Median Gross Rent) at the county level via the Census Data API.
  - URL: <https://api.census.gov/data/{vintage}/acs/acs5?get=NAME,B25064_001E&for=county:*>
  - License: U.S. public domain. API key recommended (free).
- **Lands in**: `cost_of_living_index` rows with `geo_type='county'`, source `census:acs5_b25064`. The `rpp_overall` for county rows is derived as `state_rpp × (county_rent / state_median_rent)` and labeled accordingly.
- **Ingest**: `scripts/ingest_acs_county_rents.py`.
- **Refresh**: annual (ACS 5-year vintages publish in late Q4).
- **Verification**: rural counties show RPP < state RPP; urban-core counties show RPP ≥ state RPP. Compare DC, Cook IL, Maricopa AZ, Travis TX.

### `bls_cpi` *(optional, behind a feature flag)*

- **Source**: U.S. Bureau of Labor Statistics, Consumer Price Index for Urban Consumers (CPI-U), metro-area series.
  - URL: BLS public time series API.
  - License: U.S. public domain. API key recommended (free).
- **Lands in**: `cost_of_living_index` rows with `geo_type='cbsa'`, source `bls:cpi_u`.
- **Refresh**: monthly (we read the latest annual-average value).
- **Verification**: SF / NYC / Honolulu series above national average.
- **Public-map relevance**: optional secondary signal alongside BEA RPP at the metro level. Not required for D.5.10 exit; included so future iterations can compare COL definitions.

## Basemap

### `mapbox_basemap`

- **Source**: Mapbox vector tiles (Streets v12 or a custom dark style). Token-gated.
- **License**: per Mapbox terms; free tier 50K loads/month.
- **Lands in**: not stored locally; tiles fetched at runtime by Mapbox GL JS.
- **Token security**: env var on Cloudflare Pages, restricted by URL referrer to `map.thegrandpipeline.com` and `*.pages.dev` (per ADR-0016).
- **Attribution**: "© Mapbox © OpenStreetMap" surfaced in the map UI per Mapbox terms.

## Reference: how to add a new data source

1. Pick a stable `source_key` matching the existing namespace (e.g., `opm_xyz_2026`).
2. Add the dataset to this file with all sections above.
3. Write `scripts/ingest_<source_key>.py` — must be idempotent and call into `src.data_source_registry` to record start/success/error.
4. If it has its own table or column, update `src/database.py` and bump `schema_version`.
5. Add it to `scripts/refresh_public_map_data.py` so the orchestrator includes it.
6. Surface it in `pages/11_Public_Map_Admin.py` (the page reads `data_source_status` so it picks up new keys automatically).
7. Reference the new fields in `src/public_map_export.py` if the public map should display them.
