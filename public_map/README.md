# public_map — map.thegrandpipeline.com

Static SvelteKit + Mapbox GL JS site, deployed to Cloudflare Pages. Read-only
sibling product to the local Streamlit dashboard (per ADR-0016). Fed nightly by
`scripts/export_public_map.py` writing 12 static files into `static/data/`.

## Local development

```bash
cd public_map
npm install
npm run dev
```

The dev server listens on http://localhost:5173 and serves `/map` as the canonical
map route.

The map reads its data bundle from `static/data/`. To populate it, run the export
from the dashboard repo root:

```bash
python scripts/export_public_map.py
```

If the bundle is missing, layers render empty and the manifest banner says so —
the basemap and metric switcher still work for sanity-checking the scaffold.

## Mapbox token

Copy `.env.example` to `.env` and set `VITE_MAPBOX_TOKEN` if you want the Mapbox
dark style. Without a token, the basemap falls back to an OpenStreetMap raster
source (no signup, no metering). Both paths use the same Mapbox GL JS library.

## Build

```bash
npm run build
```

`@sveltejs/adapter-static` writes a SPA into `build/`. Cloudflare Pages serves it
verbatim.

## Layer model (Phase B)

Per ADR-0017 the map is layered and zoom-driven, capped at zoom 9. From bottom
to top the layers are: basemap → states fill → counties outline → metros outline
→ localities outline + fill → marker clusters → individual markers. The
choropleth metric switcher recolors the state fill (open postings by default;
also workforce, accessions, separations, remote share, pay-vs-COL).

Phase D.5 is the active implementation queue. The map is not V1-complete until
it uses official 2026 GS pay tables, supports snap-scoped state/locality search
windows with Add to Search and global-filter preview toggles, exposes light and
dark modes, includes the personal compensation/COL comparator, shows
source-backed urgency/fill badges on job listings, and persists local
viewed/saved/hidden job state in the browser.

### Current next step: continue D.5.5 click-to-fit bounds

D.5.2 and D.5.3 shipped on 2026-05-09. The map now has code-backed agency
chips with repeated `agency=` URL state and client-only saved searches that
persist filters, metric, map viewport, and the last address-zoom target in
`localStorage`.

D.5.4 shipped on 2026-05-09. The map has a top-left address / ZIP search
control, Mapbox geocoding when a token is present, Nominatim fallback,
offline `zip_centroids.json` lookup, `flyTo`, and a transient non-job pin.
The bundle now includes 33,791 Census ZCTA centroids from
`scripts/ingest_zip_centroids.py`.

D.5.5 is now active. Polygon clicks fit the map to state, locality, county,
or metro bounds and show a Back to national pill; the remaining D.5.5 work is
visual verification plus the fuller scoped action window.
