# PUBLIC_MAP_PIPELINE.md

Operator's runbook for the Public Map Tool at `map.thegrandpipeline.com`.

The public map is a separate sibling product per ADR-0016. The dashboard reads and writes the local SQLite database; the public map only **reads** through the export script and ships static files to Cloudflare Pages.

The full external dataset catalog (where each comes from, how to refresh, schema notes) is in `docs/PUBLIC_MAP_DATA_SOURCES.md`. Status of every source at any time is visible in the local dashboard at `pages/11_Public_Map_Admin.py`.

## Data flow

```
Local SQLite (data/federal_jobs.sqlite)
  + reference data ingested by scripts/ingest_*.py:
      OPM pay tables, OPM locality definitions, OPM locality polygons,
      Census state/county/CBSA polygons, BEA RPP, etc.
  -> scripts/refresh_public_map_data.py  (orchestrator; runs every ingest)
  -> scripts/export_public_map.py        (reads DB + reference data)
  -> public_map/static/data/{
       jobs.geojson, jobs_detail.json,                       # open postings + per-job pay grids
       closed_jobs.geojson,                                  # trailing-90-days closed-postings overlay (D.5.7)
       states.geojson, localities.geojson, counties.geojson, metros.geojson,
       federal_properties.geojson,                           # GSA FRPP buildings (D.5.9, ADR-0025)
       pay_tables.json, cost_of_living.json,
       agencies.json, series.json,
       zip_centroids.json,                                   # offline ZIP geocode (D.5.4)
       manifest.json
     }
  -> git commit + git push (auto)
  -> Cloudflare Pages rebuild
  -> https://map.thegrandpipeline.com
```

The public site is read-only. No backend, no API, no auth, no DB online.

## One-time setup

Per ADR-0027 (self-bootstrapping ingests, shipped 2026-05-08), the orchestrator runs to completion from a clean checkout with **no environment variables set**. Census polygons download themselves from `www2.census.gov/geo/tiger/GENZ2023/`; ZIP/ZCTA centroids download from the Census Gazetteer; OPM locality definitions, OPM locality pay percentages, OPM GS base pay, and BEA RPP all default to checked-in seed CSVs under `data/external/{opm_locality_definitions,opm_locality_pay,opm_gs_pay,bea_rpp}/`. Env vars (`PUBLIC_MAP_*_GEOJSON`, `PUBLIC_MAP_*_CSV`) are now overrides, not enablement gates.

1. **External datasets directory.** `data/external/` already contains the seed CSVs. Other downloads land here on first run; the cached files are reused on subsequent runs. Add new vintages by replacing the seed CSV under each `<source_key>/<year>.csv` path.
2. **Geocoding seed.** Download SimpleMaps US Cities Basic CSV (CC-BY 4.0) from <https://simplemaps.com/data/us-cities>. Save to `data/external/uscities.csv`. Then:
   ```sh
   python scripts/geocode_locations.py --csv data/external/uscities.csv
   ```
3. **Reference data backfill.** Run the orchestrator:
   ```sh
   python scripts/refresh_public_map_data.py
   ```
   With no env vars, it now pulls Census TIGER polygons over HTTPS (cached after first run) and reads the checked-in seed CSVs for OPM and BEA. Every step reports ENABLED. Inspect the admin page to confirm every source is green.
4. **First export.**
   ```sh
   python scripts/export_public_map.py
   ```
   You should see polygon counts in the manifest (e.g., 56 states / 38+ localities / 3,235 counties / 935 metros) and `pay_vs_col` populated as a 60–140 purchasing-power index.
5. **Cloudflare Pages.** Connect the GitHub repo, set the build root to `public_map/`, set the Mapbox token as a build env var, add `map.thegrandpipeline.com` as a custom domain.
6. **Mapbox token hardening.** In Mapbox dashboard, restrict the token by URL referrer to `map.thegrandpipeline.com` and `*.pages.dev`.

### Annual refresh of the OPM / BEA seeds

The shipped seeds are 2025 OPM (locality definitions, locality pay %, GS base table) and 2023 BEA RPP. To refresh:

1. Replace `data/external/opm_locality_definitions/<year>.csv`, `opm_locality_pay/<year>.csv`, and `opm_gs_pay/<year>_base.csv` with files reflecting the new EO and OPM tables. Keep the same column headers (the ingest scripts validate them).
2. Replace `data/external/bea_rpp/<year>.csv` when BEA publishes a new vintage.
3. Update the `SEED_CSV` constant at the top of each ingest script to point at the new filename, OR pass `--input <path>` to override at run time.
4. Re-run `python scripts/refresh_public_map_data.py && python scripts/export_public_map.py`. The exporter's `current_reference_year` picks `MAX(year)` from `pay_scales`, so adding a new year automatically bumps the bundle's reference year.

For public-map V1, this annual refresh is not optional: official 2026 GS base and locality pay tables must be present before deploy, and `public_map/static/data/manifest.json` must report `reference_year: 2026`. Treat the checked-in 2025 OPM rows as bootstrap data for local development only.

## Admin dashboard (private)

Open the local Streamlit app and navigate to **Public Map Admin** (`pages/11_Public_Map_Admin.py`). It shows:

- Every external data source with status (green = fresh, yellow = stale, red = error or missing)
- Last successful run timestamp, row count, last error message, manual-override flag
- "Refresh" button per source — runs the corresponding ingest script
- "Upload override" — accepts a CSV/JSON for manual entry (sets `manual_override = 1`)
- Year-over-year diff for pay scales — surfaces any unexpected change before nightly export
- "Export now" button — runs `scripts/export_public_map.py` and reports bundle sizes

The admin page is **only** in the local dashboard. It is never deployed.

## Manual refresh

```sh
python scripts/refresh_public_map_data.py        # all reference datasets
python scripts/export_public_map.py              # write the bundle
git add public_map/static/data
git commit -m "data: manual refresh $(date -Iseconds)"
git push
```

Cloudflare Pages picks up the push and rebuilds within a minute or two.

## Refresh individual datasets

Each ingest script is independent. Run any one without affecting the others:

```sh
python scripts/ingest_gs_pay.py                  # OPM GS pay tables
python scripts/ingest_locality_pay.py            # OPM locality % adjustments
python scripts/ingest_locality_definitions.py    # OPM annual county-FIPS list
python scripts/ingest_locality_polygons.py       # OPM ArcGIS, falls back to dissolve
python scripts/ingest_state_polygons.py          # Census TIGER states
python scripts/ingest_county_polygons.py         # Census TIGER counties
python scripts/ingest_cbsa_polygons.py           # Census TIGER CBSAs
python scripts/ingest_bea_rpp.py                 # BEA Regional Price Parities
python scripts/ingest_other_pay_plans.py         # FW, ES, AD, FP, LE, VN, ...
python scripts/ingest_zip_centroids.py           # Census ZCTA centroids (D.5.4)
python scripts/ingest_agency_aliases.py          # curated agency-shorthand list (D.5.2)
python scripts/ingest_federal_properties.py     # GSA FRPP (D.5.9, ADR-0025)
python scripts/ingest_acs_county_rents.py        # Census ACS B25064 → county COL (D.5.10)
python scripts/ingest_bls_metro_cpi.py           # optional metro CPI overlay (D.5.10, behind a flag)
```

## Public-map corpus growth (D.5.7)

The map only becomes useful when there are enough postings to populate the heat layer and reveal patterns. Use the **Data Admin → Public Map corpus** presets (added in D.5.7) instead of the older free-form Search box when refreshing the map's job corpus:

```sh
# Through the dashboard's Data Admin page (preferred, recon-gated):
#   Federal-wide current postings (paged within USAJOBS Search rate budget)
#   Top 25 hiring agencies × current
#   HistoricJoa trailing 90 days (closed-postings overlay)
```

Each preset goes through `src/data_recon.py` first, writes its recommendation into `docs/DOWNLOAD_STRATEGY.md` per ADR-0003, and uses the standard `import_manifests` / `job_import_scopes` plumbing so the import is inspectable. The export then writes both `jobs.geojson` (open) and `closed_jobs.geojson` (closed-within-90-days).

Targets for calling D.5.7 complete:

- `manifest.json.feature_count >= 5,000` for current open posting locations.
- `manifest.json.layers["closed_jobs.geojson"] >= 5,000` for trailing-90-day closed context.
- Current Search credentials are present for the current-postings presets; HistoricJoa trailing-90-day context can run without Search credentials.

## D.5.2 agency filter verification

D.5.2 starts the next public-map step after the heat-layer and corpus-growth
partials. Before marking it complete, verify the exported agency catalog and the
browser filter use the same canonical codes:

1. Exported metadata contains each selectable agency with `code`, `name`, and
   optional aliases, with no duplicate codes.
2. Loading `/map/?agency=HSCB&agency=AG11` restores both selected agencies in the
   typeahead and preserves the repeated query keys after UI edits.
3. Selecting agencies updates the marker source, persistent heat source, feature
   panels, and `JobList.svelte` rows from the same normalized filter state.
4. Typing a known alias selects the canonical agency code; typing an unsupported
   value shows validation copy and leaves the active results unchanged.
5. Clearing all agencies returns to the unfiltered corpus without leaving stale
   URL parameters.

## Nightly cron (Windows Task Scheduler)

- **Action:** Start a program
- **Program/script:** `cmd.exe`
- **Arguments:**
  ```
  /c cd /d C:\Users\caleb\OneDrive\Desktop\Scripts\GovJobs && python scripts\refresh_public_map_data.py && python scripts\export_public_map.py && git add public_map\static\data && git commit -m "data: nightly %DATE% %TIME%" && git push
  ```
- **Run whether user is logged on or not:** yes.

Task Scheduler skips runs when the laptop is asleep. The footer's "freshness per source" makes stale snapshots obvious to public users.

## Troubleshooting

**A source is red in admin.** Click "View last error" — the error message tells you whether it's a transient network issue, a schema change, or the source moved. Fall back to manual override (CSV upload) for the year while you investigate.

**OPM ArcGIS FeatureServer is down or moved.** Per ADR-0019 the locality polygon ingest falls back to dissolving Census counties using the canonical OPM county-FIPS list. Confirm `ingest_locality_definitions.py` is green; rerun `ingest_locality_polygons.py --force-fallback`.

**Pay table values look wrong.** Open the diff view in admin — it shows year-over-year changes per (pay plan, locality, grade, step). If a value moved unexpectedly, upload an override from the published OPM PDF for that year.

**No markers on the live site.** Check `manifest.json`: `job_count == 0` means the dashboard's USAJOBS Search hasn't run recently; `location_count` much smaller than `job_count` means most jobs failed to geocode (inspect `geocoding_misses`).

**Bundle exceeds ~15 MB gzipped.** In priority order: confirm gzip is on, trim properties to codes with client-side label lookup, simplify polygon geometry further (Phase A.7 simplifies to ~10% of TIGER detail), switch the polygon layers to PMTiles vector tiles.

**Mapbox token leaked.** Bundle tokens are inherently public; mitigation is the URL referrer restriction. Rotate the token in Mapbox dashboard, update the Pages env var, trigger a rebuild.

## File responsibilities

| File / directory | Role |
| --- | --- |
| `src/database.py` | All public-map tables: `locations_geocoded`, `zip_centroids`, `pay_plans`, `pay_scales`, `locality_pay_areas`, `locality_pay_counties`, `counties`, `metro_areas`, `state_polygons`, `cost_of_living_index`, `data_source_status` |
| `src/data_source_registry.py` | Status read/update helpers |
| `src/reference_data.py` | Pure read helpers for pay/locality/COL |
| `src/pay_calculator.py` | Locality-adjusted pay tables per job |
| `src/public_map_export.py` | Pure query funcs producing dicts/lists ready for JSON |
| `scripts/ingest_*.py` | Per-source idempotent ingest |
| `scripts/refresh_public_map_data.py` | Orchestrator |
| `scripts/export_public_map.py` | Bundle writer |
| `pages/11_Public_Map_Admin.py` | Local-only admin dashboard |
| `public_map/` | SvelteKit static site (separate `package.json`) |
| `data/external/` | Downloaded raw datasets (gitignored) |
| `docs/PUBLIC_MAP_DATA_SOURCES.md` | Per-dataset catalog |
| `docs/PUBLIC_MAP_PIPELINE.md` | This file |
| `docs/DECISIONS.md` | ADR-0016, ADR-0017, ADR-0018, ADR-0019 |

## What does NOT change

- The dashboard stays local-first. ADR-0001's "no FastAPI, React, Docker, Postgres, or cloud deployment" rule still applies to everything **outside** `public_map/`.
- ADR-0002's "postings ≠ hires" labeling still applies — workforce overlays must be labeled as workforce, not postings.
- ADR-0008's "no automated applications" still applies — the public map only links out to canonical USAJOBS URLs.
- ADR-0017's maxzoom-9 cap is a load-bearing trust mechanism; it must not be relaxed without revisiting the geo_quality story.
