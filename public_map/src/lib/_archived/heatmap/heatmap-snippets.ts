// Archived 2026-05-10. See ./README.md for revival instructions.
//
// This file is NOT compiled — it sits outside the include glob (the file's
// extension is .ts but its content is annotated fragments, not a module). If
// the TypeScript service ever picks it up, wrap each block in a `void` IIFE
// or rename the extension; the live code does not import from here.

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/layers.ts
 * Location: SOURCE_IDS constant
 * ──────────────────────────────────────────────────────────────────────── */

// Add `jobsHeat: 'jobs-heat'` to SOURCE_IDS:
//
// export const SOURCE_IDS = {
//     ...
//     jobsHeat: 'jobs-heat',
//     ...
// } as const;

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/layers.ts
 * Location: LAYER_IDS constant
 * ──────────────────────────────────────────────────────────────────────── */

// Add `postingHeat: 'posting-heat'` to LAYER_IDS:
//
// export const LAYER_IDS = {
//     ...
//     postingHeat: 'posting-heat',
//     ...
// } as const;

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/layers.ts
 * Location: addAllLayers() — between the state-outline layer and the
 *           counties outline. Originally this sat at section "2."
 * ──────────────────────────────────────────────────────────────────────── */

// // 2. Posting heat surface — visible 3-9 and fed by active filters.
// map.addLayer({
//     id: LAYER_IDS.postingHeat,
//     type: 'heatmap',
//     source: SOURCE_IDS.jobsHeat,
//     minzoom: 3,
//     maxzoom: 9,
//     paint: {
//         'heatmap-weight': [
//             'interpolate',
//             ['linear'],
//             ['to-number', ['get', 'salary_min'], 0],
//             0,
//             0.65,
//             150000,
//             1.1
//         ],
//         'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.7, 7, 1.4, 9, 1.0],
//         'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 18, 7, 28, 9, 20],
//         'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.55, 7, 0.25, 9, 0.25],
//         'heatmap-color': [
//             'interpolate',
//             ['linear'],
//             ['heatmap-density'],
//             0,
//             'rgba(28, 42, 64, 0)',
//             0.2,
//             '#2c5b8a',
//             0.45,
//             '#4979b3',
//             0.7,
//             '#7bd0f2',
//             1,
//             '#fff2a8'
//         ]
//     }
// });
// map.moveLayer(LAYER_IDS.statesOutline);

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/layers.ts
 * Location: end of file — exported helper used by Map.svelte
 * ──────────────────────────────────────────────────────────────────────── */

// export function setPostingHeatVisible(map: MaplibreMap, visible: boolean): void {
//     if (!map.getLayer(LAYER_IDS.postingHeat)) return;
//     const opacity: ExpressionSpecification | number = visible
//         ? (['interpolate', ['linear'], ['zoom'], 3, 0.55, 7, 0.25, 9, 0.25] as ExpressionSpecification)
//         : 0;
//     map.setPaintProperty(
//         LAYER_IDS.postingHeat,
//         'heatmap-opacity',
//         opacity as unknown as ExpressionSpecification
//     );
// }

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/store.svelte.ts
 * Location: MapState class field
 * ──────────────────────────────────────────────────────────────────────── */

// postingHeatEnabled = $state<boolean>(true);

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/Map.svelte
 * Location: import block at the top
 * ──────────────────────────────────────────────────────────────────────── */

// // Add to the existing layers.ts import:
// import {
//     ...,
//     setPostingHeatVisible,
//     ...
// } from './layers';

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/Map.svelte
 * Location: onMount(...) → map.on('load', ...) — initial source set-up
 * ──────────────────────────────────────────────────────────────────────── */

// // Sat between the localities source add and the closed-jobs source add.
// addOrUpdateSource(map, SOURCE_IDS.jobsHeat, filteredJobs);

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/Map.svelte
 * Location: $effect that reacts to metric / shading / closed / FRPP toggles
 * ──────────────────────────────────────────────────────────────────────── */

// const heatOn = mapState.postingHeatEnabled;
// // ...
// setPostingHeatVisible(map, heatOn);

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/Map.svelte
 * Location: $effect that reacts to filter / hidden-jobs changes
 * ──────────────────────────────────────────────────────────────────────── */

// // Sat alongside the closed-jobs and clustered-jobs source updates.
// addOrUpdateSource(map, SOURCE_IDS.jobsHeat, filteredJobs);

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/MetricSwitcher.svelte
 * Location: <script> block
 * ──────────────────────────────────────────────────────────────────────── */

// function toggleHeat() {
//     mapState.postingHeatEnabled = !mapState.postingHeatEnabled;
// }

/* ────────────────────────────────────────────────────────────────────────
 * From: public_map/src/lib/MetricSwitcher.svelte
 * Location: title-row inside the .switcher container, between the Shade
 *           toggle and the Closed toggle
 * ──────────────────────────────────────────────────────────────────────── */

// <button
//     type="button"
//     class="shade-toggle"
//     class:on={mapState.postingHeatEnabled}
//     onclick={toggleHeat}
//     aria-pressed={mapState.postingHeatEnabled}
//     title={mapState.postingHeatEnabled ? 'Posting heat is on' : 'Posting heat is off'}
// >
//     Heat {mapState.postingHeatEnabled ? 'on' : 'off'}
// </button>
