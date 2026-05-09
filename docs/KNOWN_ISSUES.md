# KNOWN_ISSUES.md

Open bugs and inconsistencies that need fixing. Each entry: what's broken, where, and how it manifests. Append-only; remove an entry when the fix lands.

---

## 1. Three `tests/test_public_map_export.py` tests fail with `KeyError: 'geo_quality'`

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

## 2. `vitest` types missing in public_map svelte-check

**Where:** `public_map/src/lib/basemap.test.ts:12` and `public_map/src/lib/compensation.test.ts:3`

**Symptom:** `npm run check` reports 2 errors / 0 warnings, both: `Cannot find module 'vitest' or its corresponding type declarations.` `npm test` (vitest) still passes; `npm run build` still passes. Type-check noise only.

**Status:** pre-existing — package-lock was synced for vitest in commit `4f4085e` but `node_modules` may not include the type declarations on every workstation. Confirmed during D.5.10 work on 2026-05-09.

**Fix options:**
- Run `npm install` in `public_map/` — the simplest path if the lockfile is correct.
- Add `"types": ["vitest/globals"]` to `public_map/tsconfig.json` if vitest's types aren't auto-resolved.
- Or move the test files outside the svelte-check scan (e.g. via an `exclude` in `tsconfig.json`) and rely on vitest's own typecheck.
