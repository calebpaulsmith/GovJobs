# public_map — thegrandpipeline.com/map

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

## Layer model

Per ADR-0017 the map is layered and zoom-driven, capped at zoom 9. From bottom
to top the layers are: basemap → states fill → counties outline → metros outline
→ localities outline + fill → marker clusters → individual markers. The
choropleth metric switcher recolors the state fill (open postings by default;
also workforce, accessions, separations, remote share, pay-vs-COL).

Current implementation includes the Phase C click/popup components and Phase D filter URL state. Phase F operations/polish has started with an `/about` route, attribution/disclaimer content, social-preview metadata, `robots.txt`, and `sitemap.xml`.

## Operations and public metadata

The static site now ships the first Phase F public-surface assets:

- `/about` documents data sources, precision limits, and the no-affiliation disclaimer.
- `robots.txt` allows indexing and points crawlers to `sitemap.xml`.
- `sitemap.xml` lists `/map` and `/about`.
- `og-image.svg` plus Open Graph/Twitter metadata provide a share preview for the public map.
