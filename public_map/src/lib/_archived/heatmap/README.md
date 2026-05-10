# Archived: posting heat-map layer

**Removed from the live map on 2026-05-10.** Operator review on the same date
flagged that the heat-map intensity didn't visually correlate with the marker
positions, particularly at zoom 4–7 where the heat radius was wide enough to
spread density into areas where no actual postings sat.

The original heat-map layer was a Mapbox `heatmap` layer fed by a separate
`jobs-heat` source (kept distinct from the clustered `jobs` source so heat
density was driven by raw point counts rather than cluster aggregation).

This folder preserves the code so the feature can be revived later without
having to reverse-engineer it from git history. The snippet file mirrors the
shape of the live `layers.ts` / `Map.svelte` / `MetricSwitcher.svelte` /
`store.svelte.ts` modules at the time of removal.

## Files

- `heatmap-snippets.ts` — verbatim TypeScript / Svelte fragments extracted
  from the four files that referenced the heat-map. Each fragment is annotated
  with the file it came from and the surrounding context, so reinstating it is
  a matter of pasting back into the indicated locations and re-running the
  test suite.

## How to revive

1. Open `heatmap-snippets.ts` and copy each labelled fragment back into its
   original file at the location indicated by the comment header.
2. Re-add the `posting-heat` layer to the layer order documented in
   `public_map/src/lib/layers.ts::addAllLayers` (it sat between the state
   choropleth and the polygon outlines).
3. Re-add `setPostingHeatVisible` to the `$effect` block in `Map.svelte` that
   reacts to metric / shading / heat / closed-jobs / FRPP toggles.
4. Re-add the `Heat on/off` pill button to `MetricSwitcher.svelte`.
5. Re-add `postingHeatEnabled = $state<boolean>(true)` to `store.svelte.ts`.
6. Run `npm run check && npm test && npm run build` to confirm nothing regressed.

## Why not just keep it disabled?

Two reasons:

- The toggle was permanently visible in the metric switcher and read as a
  promise that the data was meaningful when, on inspection, the heat surface
  did not align with the actual job clusters. Hiding the toggle behind a flag
  would still ship the layer's source-fetch cost on every page load.
- Removing the live code path lets us improve the markers + cluster UX
  (street-level zoom shipped in the same change) without keeping a deprecated
  visualization in lockstep.

If a future iteration wants a density visualization, the most likely correct
path is **kernel density on a hex grid driven by the actual job point set**,
not the per-marker heat radius approach archived here.
