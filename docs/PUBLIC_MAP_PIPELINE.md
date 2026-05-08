# PUBLIC_MAP_PIPELINE.md

Operator's runbook for the Public Map Tool at `thegrandpipeline.com/map`.

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
  -> https://thegrandpipeline.com/map
```

The public site is read-only. No backend, no API, no auth, no DB online.

## One-time setup

1. **External datasets directory.** Make sure `data/external/` exists; this is where downloaded raw datasets land. Gitignored.
2. **Geocoding seed.** Download SimpleMaps US Cities Basic CSV (CC-BY 4.0) from <https://simplemaps.com/data/us-cities>. Save to `data/external/uscities.csv`. Then:
   ```sh
   python scripts/geocode_locations.py --csv data/external/uscities.csv
   ```
3. **Reference data backfill.** Run the orchestrator:
   ```sh
   python scripts/refresh_public_map_data.py
   ```
   It pulls every supported reference dataset and updates `data_source_status`. Inspect the admin page to confirm every source is green.
4. **First export.**
   ```sh
   python scripts/export_public_map.py
   ```
5. **Cloudflare Pages.** Connect the GitHub repo, set the build root to `public_map/`, set the Mapbox token as a build env var, add `thegrandpipeline.com` as a custom domain.
6. **Mapbox token hardening.** In Mapbox dashboard, restrict the token by URL referrer to `thegrandpipeline.com` and `*.pages.dev`.

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
python scripts/ingest_zip_centroids.py           # SimpleMaps US ZIPs (D.5.4)
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

Each preset goes through `src/data_recon.py` first, writes its recommendation into `docs/DOWNLOAD_STRATEGY.md` per ADR-0003, and uses the standard manifest plumbing so the import is resumable. The export then writes both `jobs.geojson` (open) and `closed_jobs.geojson` (closed-within-90-days).

All idempotent. All write a row to `data_source_status` so the admin page reflects the new state.

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
| `src/database.py` | All public-map tables: `locations_geocoded`, `pay_plans`, `pay_scales`, `locality_pay_areas`, `locality_pay_counties`, `counties`, `metro_areas`, `state_polygons`, `cost_of_living_index`, `data_source_status` |
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
