# KNOWN_ISSUES.md

Open bugs and inconsistencies that need fixing. Each entry: what's broken, where, and how it manifests. Append-only; remove an entry when the fix lands.

---

## How to view the deployed public map and reproduce these issues

**Live URL:** https://map.thegrandpipeline.com/map (Cloudflare Pages, custom domain).

**Five-minute smoke procedure:**

1. Open the live URL in any modern browser. Within ~5 s the U.S. basemap should render with thousands of clustered job markers, the masthead pill ("The Grand Pipeline"), the metric switcher (`Postings` / `Workforce` / …) at the bottom, and the Filters / Saved searches / Address widgets at top-left. If the page loads but markers never appear, open DevTools → Network and confirm `/data/jobs.geojson` returns 200; if it 404s the bundle wasn't exported.
2. Hit the Posting Intelligence Function directly from DevTools → Console (with `location.origin` already on the deployed host):
   ```js
   const u = new URL('/api/job-history', location.origin);
   u.searchParams.set('agency_code', 'HSCB');
   u.searchParams.set('window', '1mo');
   fetch(u).then(r => r.json()).then(j => ({status: j.status, total: j.total, monthly: j.monthly?.length}));
   ```
   Expect `{status: 'ok', total: <N>, monthly: <M>}`. `status: 'unavailable'` means the upstream HistoricJoa rejected us — error reason is in `j.error`. Hit the same URL twice and check `cf-cache-status` — second call should be `HIT`.
3. Click any cluster until it expands to a single marker, then click the marker. The right-side JobCard appears.
4. Scroll to the bottom of the JobCard and click "▸ Posting Intelligence". The first click loads the default 1-yr window: confirm a small bar timeline renders and the summary line says `<N> matching postings · <start> → <end>`.
5. Click each window pill (1mo, 3mo, …, 10yr) — each should re-fetch and refresh the timeline. Then click "See all N matching historic postings" — paginated 25-row list expands; Prev / Next buttons should work.

Pre-existing bug reproductions:

- **Issue #3 / #4 (test-only):** `cd public_map && npm test`. With both fixes landed (vitest.config.ts override + chunkSizeWarningLimit raise), expect 47/47 pass and no chunk-size warning during `npm run build`.
- **Issue #1 (test-only):** `python -m pytest tests/test_public_map_export.py`. With the geo_quality re-add landed, expect 27/27 pass.

---

## 1. ~~Three `tests/test_public_map_export.py` tests fail with `KeyError: 'geo_quality'`~~ — **RESOLVED 2026-05-09**

**Fix:** `_feature_from_marker` in `src/public_map_export.py` now emits `geo_quality` on every marker feature. Adds ~30 KB gzipped to `jobs.geojson` in exchange for surfacing whether a marker landed on USAJOBS source coords, a city centroid, or a state centroid. All 27 tests in `tests/test_public_map_export.py` pass.

---

## 1 (original report).

**Where:** `tests/test_public_map_export.py`
- `test_jobs_geojson_prefers_job_locations_lat_lon_over_geocoded` (line ~117)
- `test_jobs_geojson_uses_city_match_when_available` (line ~160)
- `test_jobs_geojson_falls_back_to_state_centroid` (line ~182)

**Symptom:** `KeyError: 'geo_quality'` — the tests assert `feature["properties"]["geo_quality"]` equals `"source"` / `"city"` / `"state_centroid"`, but `_feature_from_marker` in `src/public_map_export.py` no longer emits that property. Marker properties now: `id, agency_code, series, grade_low, grade_high, pay_plan, salary_min, remote_status, close_date, city, state, locality_code` plus optional `status` / `closed_within_days` for closed-jobs features.

**Status:** pre-existing on `master` (verified by stashing D.5.10 changes and re-running). Discovered while running the full pytest suite during D.5.10 work on 2026-05-09.

**Fix options:**
- Drop `geo_quality` from the test assertions if the property is intentionally gone (the marker dataset still computes it internally for the marker selection logic but it is not exposed to the bundle).
- Or re-add `geo_quality` to the emitted feature properties — useful debugging signal for users wondering why a marker landed on a state centroid versus a city centroid.

The `_marker_dataset` query already computes `geo_quality` in its SELECT — `_feature_from_marker` just doesn't read it. So re-adding is one line.

---

## 2. ~~`vitest` types missing in public_map svelte-check~~ — **RESOLVED 2026-05-09**

**Fix:** Resolved by `npm install` in `public_map/` — the lockfile was already correct. `npm run check` now reports 0 errors / 0 warnings on a fresh install.

---

## 2 (original report).

**Where:** `public_map/src/lib/basemap.test.ts:12` and `public_map/src/lib/compensation.test.ts:3`

**Symptom:** `npm run check` reports 2 errors / 0 warnings, both: `Cannot find module 'vitest' or its corresponding type declarations.` `npm test` (vitest) still passes; `npm run build` still passes. Type-check noise only.

**Status:** pre-existing — package-lock was synced for vitest in commit `4f4085e` but `node_modules` may not include the type declarations on every workstation. Confirmed during D.5.10 work on 2026-05-09.

**Fix options:**
- Run `npm install` in `public_map/` — the simplest path if the lockfile is correct.
- Add `"types": ["vitest/globals"]` to `public_map/tsconfig.json` if vitest's types aren't auto-resolved.
- Or move the test files outside the svelte-check scan (e.g. via an `exclude` in `tsconfig.json`) and rely on vitest's own typecheck.

---

## 3. ~~`basemap.test.ts` — two assertions fail when `public_map/.env` ships with a Mapbox token~~ — **RESOLVED 2026-05-09**

**Fix:** Added `test.env: { VITE_MAPBOX_TOKEN: '' }` and `envDir: false` to `public_map/vitest.config.ts`. The vitest run now starts with an empty token regardless of what `.env` ships, so the no-token assertions exercise the OSM-fallback branch they were designed for. `npm test` reports 47/47 pass.

---

## 3 (original report).

**Where:** `public_map/src/lib/basemap.test.ts`
- `configureMapboxRuntime > drops REQUIRE_ACCESS_TOKEN when no Mapbox token is present` (~line 96)
- `pickStyleForTheme > returns inline OSM styles when no token is configured` (~line 104)

**Symptom:** `npm test` reports 2 failed / 45 passed. The failing assertions assume `import.meta.env.VITE_MAPBOX_TOKEN` is empty, but the user's checked-in `public_map/.env` defines a real token, which Vite/Vitest loads automatically via the SvelteKit-style `.env` resolution. So the no-token code path is never reached during tests.

**Status:** pre-existing — verified by stashing the D.5.24 changes and re-running; same two failures appear on master. Discovered while shipping D.5.24 on 2026-05-09.

**Fix options:**
- Wrap the no-token assertions in `vi.stubEnv('VITE_MAPBOX_TOKEN', '')` + `vi.unstubAllEnvs()` in `afterEach`, so the test forces the no-token branch regardless of what `.env` ships.
- Or add a `vitest.config.ts` `test.env: { VITE_MAPBOX_TOKEN: '' }` override so the whole test run starts without a token.
- Or add `define: { 'import.meta.env.VITE_MAPBOX_TOKEN': '""' }` in `vitest.config.ts` so `.env` is ignored at test time.

The token loading behavior in production is correct — only the test isolation is wrong.

---

## 4. ~~mapbox-gl chunk crosses the 500 kB warning threshold~~ — **RESOLVED 2026-05-09**

**Fix:** `public_map/vite.config.ts` now sets `build.chunkSizeWarningLimit: 2000`. The `manualChunks` route was tried first and rejected because SvelteKit's SSR build externalizes `mapbox-gl`. Raising the threshold is the correct call — Mapbox is core to the product and the chunk gzips down to ~492 KB on the wire. `npm run build` is now warning-free.

---

## 4 (original report).

**Where:** `public_map/` production build, chunk `_app/immutable/chunks/C9TVsRsc.js` (hash varies per build).

**Symptom:** `npm run build` prints a Vite warning: chunk is **1,782 kB** (gzip 492 kB), exceeding the default 500 kB threshold. The build still succeeds. mapbox-gl is the dominant contributor.

**Status:** pre-existing — flagged in every recent build log. Not a regression from D.5.24.

**Fix options:**
- Code-split mapbox-gl via dynamic `import('mapbox-gl')` (already used inside `Map.svelte::onMount`); the warning is about the chunk's *total* size, not its load time. Adding `build.rollupOptions.output.manualChunks: { mapboxgl: ['mapbox-gl'] }` in `vite.config.ts` would isolate it into its own named chunk so it's easier to inspect.
- Or simply raise `build.chunkSizeWarningLimit` to 2_000 in `vite.config.ts` and accept the size — Mapbox is core to the product, splitting it harder doesn't reduce wire bytes.

---

## 5. D.5.24 Posting Intelligence — first live deploy returned `status: 'unavailable'` for every query

**Where:** `public_map/functions/api/job-history.ts`.

**Symptom:** First live test against `https://map.thegrandpipeline.com/api/job-history?agency_code=HSCB&window=1mo` returned `200 OK` with body `{status: 'unavailable', total: 0, monthly: [], …}` even though the Function deployed correctly and routed correctly (`cf-cache-status: DYNAMIC`). The upstream HistoricJoa call was failing.

**Root cause:** The Function sent `User-Agent: thegrandpipeline-map/job-history` to USAJOBS. Per USAJOBS's public API docs the User-Agent header must contain a contact email; non-email values are rejected. The Function also lacked `Host: data.usajobs.gov` and `Accept: application/hr+json`, both of which the dashboard's local importer (`src/data_import.py::usajobs_headers`) sends.

**Fix landed 2026-05-09:** In `public_map/functions/api/job-history.ts`:
- `UPSTREAM_USER_AGENT` now resolves to `thegrandpipeline-map (calebpaulsmith@gmail.com)` (a contact-style identifier).
- The upstream `fetch()` now also sends `Host: data.usajobs.gov` and `Accept: application/hr+json`.
- Failure path now includes the upstream response body (truncated to 200 chars) in the error message so the next debugging round is faster.
- `UPSTREAM_TIMEOUT_MS` raised from 8 s → 20 s; cold HistoricJoa hits regularly take 5–10 s.

**Verified live 2026-05-09 22:15Z** against `https://map.thegrandpipeline.com/api/job-history` after redeploy:
- Cold call (HSCB / 6mo): 4.9 s, `status: 'ok'`, total = 106, 5 monthly buckets.
- Cold call (HSCB / 1yr): 4.3 s, `status: 'ok'`, total = 405, 11 monthly buckets.
- Edge cache (HE38 / 6mo): cold 3.9 s → warm 2 ms (1900× speedup, `status: 'ok'`, total = 163).
- JobCard end-to-end: opened a Wildland Fire posting in McDermitt NV, expanded Posting Intelligence — query was built correctly from `mapState.filters` ∪ JobCard fields (`agency IN01 · series 6907 · grade 6 · state NV`), 1 yr default rendered 2 timeline bars + drill-in button. Switching to the 5 yr pill re-fired the upstream call and updated the panel.

**Spinoff issues uncovered during the live test — both fixed 2026-05-09:**
- ~~Two of three sampled agency codes (`TRDA`, `NN16`) returned upstream payloads that JSON-parsed as empty (Function reported `Unexpected end of JSON input`).~~ **Fixed:** the Function now reads the upstream as text first, treats an empty body as `{data: []}`, and only fails when there is content that fails to parse as JSON. Agencies with zero matching postings now correctly return `{status: 'ok', total: 0, monthly: []}`.
- ~~The Function's failure cache TTL is 5 min by design but burned in cached failures from the pre-User-Agent-fix deployment, so the first wave of post-redeploy queries served stale `unavailable` responses for ~5 min.~~ **Fixed:** the cache key now includes the first 7 chars of `env.CF_PAGES_COMMIT_SHA` (auto-populated by Cloudflare Pages). Each deploy gets a fresh cache namespace, so old cached payloads — including failures — are silently bypassed on the first request after a deploy. The 24h success TTL is preserved for performance within a single deploy.

**Fix / verification checklist (run in order against the live deploy):**
1. `curl -sS 'https://<canonical-host>/api/job-history?agency_code=HSCB&window=1mo' | head -c 800` — expect `{"status":"ok","window":"1mo",...}`. A `<!DOCTYPE html>` response means the SPA fallback caught the path (Functions not deployed; see fix below).
2. Open a JobCard, expand "Posting Intelligence", click each window pill, and watch DevTools → Network for one `/api/job-history?...&window=…` request per click; second click on the same window should be a cache hit (CF-Cache-Status: HIT).
3. Click "See all N matching historic postings" — confirm the paginated list renders 25 rows / page and Prev/Next work.
4. With **no filters set** and a JobCard whose `agency_code` is also blank, confirm the request still completes (it falls through to a date-range-only HistoricJoa query) — and that the `truncated: true` badge appears when the 5-page (~2,500 record) cap fires.
5. Confirm the 24h edge cache works: hit `/api/job-history?agency_code=HSCB&window=1yr` twice with a 5+ second gap; the second response should arrive in &lt;100 ms.

**Suspected gotchas to look for during verification:**
- **Routing.** With SvelteKit's `adapter-static` we ship `index.html` as the SPA fallback. Cloudflare Pages auto-discovers `functions/api/job-history.ts` and routes `/api/job-history` to the worker *before* the SPA fallback — but only if the directory is named `functions/` at the project root and the build output is in `build/`. If `/api/job-history` returns the HTML SPA, add a `_routes.json` to the root (or to `static/`) with `{ "version": 1, "include": ["/api/*"], "exclude": [] }` so Pages knows to bypass static for `/api/*`.
- **TypeScript bundling.** The Function imports `'../../src/lib/jobHistory'` (no `.ts` extension). Cloudflare Pages' esbuild step resolves `.ts` automatically, but if the build logs show `Cannot resolve module`, change the import to `'../../src/lib/jobHistory.ts'` or copy the helper into `functions/`.
- **Workers types.** I declared a minimal `PagesContext` instead of pulling in `@cloudflare/workers-types`. That's fine for typecheck but means `request.cf`, `env`, and proper `EventContext<...>` generics are not available. If we add other Functions, install `@cloudflare/workers-types` and switch to the official types.
- **Empty-filter floods.** If a user opens Posting Intelligence on a JobCard with no `agency_code` *and* no active filter chips, the upstream call has only a date range. For a 10-yr window that returns *every federal posting* in the last decade — capped at 2,500 by our 5-page limit but still a lot of upstream load per cache miss. Consider requiring at least one of agency / series / state to be set before allowing load; show a "Set a filter chip first" hint instead.
- **HistoricJoa 8 s timeout.** The Function aborts the upstream after 8 s. HistoricJoa's first cold response can be slower; if users see "history unavailable" frequently on first hits, raise the timeout to 15–20 s (still well under Cloudflare's 30 s Function limit).
- **`mapState.theme` flash.** Pre-existing minor: `mapState.theme` defaults to `'dark'` server-side and the inline pre-paint script in `app.html` swaps to the persisted value — but D.5.16 verified this works. Mentioning here only because the new PostingIntelligence panel uses CSS custom properties; verify both modes look right after expansion.

---

## 6. Posting Intelligence query inheritance — JobCard fields override `mapState.filters` blanks but not the inverse

**Where:** `public_map/src/lib/PostingIntelligence.svelte::buildQuery()`

**Symptom (intentional but worth flagging):** the precedence order is *active filter chip wins; otherwise fall back to the host posting's field*. So if the user has filtered to series `0301` and clicks a posting that's series `0343`, the timeline reflects `0301` (the filter), not `0343` (the posting). This matches ADR-0029 ("inherits `mapState.filters` as single source of truth") but may surprise users who expect the panel to describe "this exact posting's history."

**Status:** open question, not yet a bug. If user testing surfaces confusion, add a small "viewing history for: agency=HSCB · series=0301" summary above the timeline (the panel already prints `describeQuery()` — make it more prominent) or add a "this posting's exact context" toggle that swaps to JobCard fields only.


